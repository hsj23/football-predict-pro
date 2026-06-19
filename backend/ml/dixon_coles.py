"""
Dixon-Coles 进球预测模型
基于 Poisson 分布 + Dixon-Coles ρ参数修正低比分平局低估
参考文献: Dixon & Coles (1997) "Modelling Association Football Scores and Inefficiencies in the Football Betting Market"
"""
import json, os, logging
import numpy as np
from math import exp, log, factorial
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')


class DixonColesModel:
    """
    Dixon-Coles 模型:
    - 每队进球数服从 Poisson(λ)
    - λ_home = exp(attack_home + defence_away + home_advantage)
    - λ_away = exp(attack_away + defence_home)
    - ρ 参数修正 (0,0), (0,1), (1,0), (1,1) 四个低比分结果的联合概率
    """

    def __init__(self):
        self.team_params = {}  # team -> {'attack': float, 'defence': float}
        self.home_advantage = 0.25  # log-scale home advantage (~+0.28 goals)
        self.rho = -0.13  # Dixon-Coles 依赖参数 (负值表示低比分平局被独立Poisson低估)
        self.fitted = False
        self._load_or_fit()

    def _load_or_fit(self):
        """尝试加载已拟合的参数，否则从训练数据拟合"""
        param_file = os.path.join(DATA_DIR, 'dixon_coles_params.json')
        if os.path.exists(param_file):
            try:
                with open(param_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.team_params = data.get('team_params', {})
                self.home_advantage = data.get('home_advantage', 0.25)
                self.rho = data.get('rho', -0.13)
                self.fitted = True
                logger.info(f"已加载 Dixon-Coles 参数: {len(self.team_params)} 队")
                return
            except Exception as e:
                logger.warning(f"加载 Dixon-Coles 参数失败: {e}")

        self._fit_from_training_data()

    def _fit_from_training_data(self):
        """从 training_data.json 用极大似然估计拟合参数"""
        train_file = os.path.join(DATA_DIR, 'training_data.json')
        if not os.path.exists(train_file):
            logger.warning("无训练数据，使用默认参数")
            return

        try:
            with open(train_file, 'r', encoding='utf-8') as f:
                matches = json.load(f)

            if len(matches) < 100:
                logger.warning(f"训练数据不足 ({len(matches)} 场)")
                return

            logger.info(f"从 {len(matches)} 场比赛拟合 Dixon-Coles 参数...")

            # 收集所有队伍
            teams = set()
            valid_matches = []
            for m in matches:
                home = m.get('home', '').strip()
                away = m.get('away', '').strip()
                hs = m.get('home_score')
                ags = m.get('away_score')
                if not home or not away or hs is None or ags is None:
                    continue
                hs, ags = int(hs), int(ags)
                # 过滤异常比分（>10球可能是错误数据）
                if hs > 10 or ags > 10:
                    continue
                teams.add(home)
                teams.add(away)
                valid_matches.append((home, away, hs, ags))

            teams = sorted(teams)
            n_teams = len(teams)
            team_to_idx = {t: i for i, t in enumerate(teams)}

            logger.info(f"  {n_teams} 队, {len(valid_matches)} 场有效比赛")

            # 使用 scipy L-BFGS-B 优化极大似然
            from scipy.optimize import minimize

            n_teams_val = n_teams
            team_to_idx_val = team_to_idx
            valid_matches_val = valid_matches
            rho = self.rho

            def neg_loglik(params):
                """负对数似然（scipy minimize 最小化目标）"""
                total = 0.0
                attack = params[:n_teams_val]
                defence = params[n_teams_val:2*n_teams_val]
                gamma = params[-1]

                for home, away, hs_g, ags_g in valid_matches_val:
                    hi = team_to_idx_val[home]
                    ai = team_to_idx_val[away]

                    log_lh = attack[hi] + defence[ai] + gamma
                    log_la = attack[ai] + defence[hi]

                    lh = max(exp(log_lh), 1e-8)
                    la = max(exp(log_la), 1e-8)

                    prob = DixonColesModel._dc_prob(hs_g, ags_g, lh, la, rho)
                    total -= log(max(prob, 1e-15))

                return total

            # 初始值: 零向量 + home_adv=0.25
            x0 = np.zeros(n_teams * 2 + 1)
            x0[-1] = 0.25

            # 约束: sum(attack) = 0
            from scipy.optimize import LinearConstraint
            A = np.zeros((1, len(x0)))
            A[0, :n_teams] = 1.0
            constraint = LinearConstraint(A, 0, 0)

            logger.info("  使用 L-BFGS-B 优化...")
            result = minimize(
                neg_loglik, x0,
                method='L-BFGS-B',
                jac=None,
                constraints=constraint,
                options={'maxiter': 200, 'disp': False, 'ftol': 1e-8},
            )

            params = result.x
            logger.info(f"  优化完成: log-likelihood = {-result.fun:.1f}, 迭代={result.nit}")

            # 保存参数
            for i, team in enumerate(teams):
                self.team_params[team] = {
                    'attack': float(params[i]),
                    'defence': float(params[i + n_teams]),
                }
            self.home_advantage = float(params[-1])
            self.fitted = True

            logger.info(f"拟合完成: {n_teams} 队, home_adv={self.home_advantage:.3f}, rho={self.rho}")
            self._save_params()

        except Exception as e:
            logger.error(f"拟合 Dixon-Coles 失败: {e}", exc_info=True)
            self.team_params = {}
            self.fitted = False

    def _save_params(self):
        param_file = os.path.join(DATA_DIR, 'dixon_coles_params.json')
        with open(param_file, 'w', encoding='utf-8') as f:
            json.dump({
                'team_params': self.team_params,
                'home_advantage': self.home_advantage,
                'rho': self.rho,
            }, f, ensure_ascii=False)

    @staticmethod
    def _tau(hg, ag, lambda_h, lambda_a, rho):
        """Dixon-Coles τ 修正项"""
        if hg == 0 and ag == 0:
            return 1 - lambda_h * lambda_a * rho
        elif hg == 0 and ag == 1:
            return 1 + lambda_h * rho
        elif hg == 1 and ag == 0:
            return 1 + lambda_a * rho
        elif hg == 1 and ag == 1:
            return 1 - rho
        return 1.0

    @staticmethod
    def _dc_prob(hg, ag, lambda_h, lambda_a, rho):
        """Dixon-Coles 联合概率 P(hg, ag)"""
        p_h = exp(-lambda_h) * lambda_h ** hg / factorial(hg)
        p_a = exp(-lambda_a) * lambda_a ** ag / factorial(ag)
        tau = DixonColesModel._tau(hg, ag, lambda_h, lambda_a, rho)
        return p_h * p_a * tau

    def get_team_strength(self, team: str) -> Tuple[float, float]:
        """返回 (attack, defence) 参数"""
        if team in self.team_params:
            p = self.team_params[team]
            return p['attack'], p['defence']
        return 0.0, 0.0  # 默认平均

    def predict_goals(self, home: str, away: str, elo_h: float = 1500, elo_a: float = 1500) -> Dict:
        """
        预测两队的期望进球和比分概率分布
        返回: {lambda_home, lambda_away, score_probs, result_probs}
        """
        att_h, def_h = self.get_team_strength(home)
        att_a, def_a = self.get_team_strength(away)

        # 如果队伍不在参数中，用Elo估算（按比例缩放到attack/defence范围）
        if att_h == 0 and def_h == 0 and elo_h != 1500:
            att_h = (elo_h - 1500) / 800 * 0.4
            def_h = (elo_h - 1500) / 800 * 0.2
        if att_a == 0 and def_a == 0 and elo_a != 1500:
            att_a = (elo_a - 1500) / 800 * 0.4
            def_a = (elo_a - 1500) / 800 * 0.2

        log_lambda_h = att_h + def_a + self.home_advantage
        log_lambda_a = att_a + def_h

        lambda_h = exp(log_lambda_h)
        lambda_a = exp(log_lambda_a)

        # 计算比分概率矩阵 (0~7球)
        max_goals = 7
        score_probs = np.zeros((max_goals + 1, max_goals + 1))

        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                score_probs[i, j] = self._dc_prob(i, j, lambda_h, lambda_a, self.rho)

        # 归一化（截断到 7 球）
        total = score_probs.sum()
        if total > 0:
            score_probs /= total

        # 胜平负概率
        home_prob = score_probs[np.triu_indices(max_goals + 1, 1)].sum()
        draw_prob = score_probs.diagonal().sum()
        away_prob = score_probs[np.tril_indices(max_goals + 1, -1)].sum()

        # 常见比分
        common_scores = []
        for i in range(5):
            for j in range(5):
                common_scores.append((i, j, float(score_probs[i, j])))
        common_scores.sort(key=lambda x: -x[2])

        return {
            'lambda_home': round(lambda_h, 2),
            'lambda_away': round(lambda_a, 2),
            'expected_home_goals': round(lambda_h, 2),
            'expected_away_goals': round(lambda_a, 2),
            'most_likely_score': f"{common_scores[0][0]}-{common_scores[0][1]}",
            'result_probs': {
                'home': round(home_prob * 100, 1),
                'draw': round(draw_prob * 100, 1),
                'away': round(away_prob * 100, 1),
            },
            'top_scores': [{'score': f'{i}-{j}', 'prob': round(p * 100, 2)}
                           for i, j, p in common_scores[:5]],
        }

    def predict(self, home: str, away: str, league: str = '') -> Dict:
        """主要接口：预测胜平负 + 比分"""
        goals = self.predict_goals(home, away)
        rp = goals['result_probs']

        # 选择预测方向
        best = max(rp, key=rp.get)
        conf = rp[best]

        names = {'home': '主胜', 'draw': '平局', 'away': '客胜'}

        return {
            'prediction': best,
            'prediction_name': names[best],
            'confidence': conf,
            'probabilities': rp,
            'predicted_score': goals['most_likely_score'],
            'expected_goals': {
                'home': goals['expected_home_goals'],
                'away': goals['expected_away_goals'],
            },
            'model': 'dixon_coles',
        }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    dc = DixonColesModel()
    result = dc.predict('拜仁慕尼黑', '多特蒙德')
    print(f"\n拜仁 vs 多特: {result['prediction_name']} ({result['confidence']:.1f}%)")
    print(f"期望进球: {result['expected_goals']}")
    print(f"概率: {result['probabilities']}")
    print(f"最可能比分: {result['predicted_score']}")
