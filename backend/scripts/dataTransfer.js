var dataTransferClass = {
    curSelectedGame: '',  //当前选择的玩法
    curSportType: 1,  //当前运动类型：1：足球；2：篮球
    matchIdList: '',  //请求支持比率mid列表
    //调用计算器对阵数据接口
    getJsqMatchDate: function (pool, stype){
        if(pool) dataTransferClass.curSelectedGame = pool;
        if(stype) dataTransferClass.curSportType = stype;
        var apiurl = jsCommonDataV1.webApi+'/gateway/uniform/football/getMatchCalculatorV1.qry?channel='+commonV1Fun.comDataChannel;
        if(dataTransferClass.curSportType == 2){
            apiurl = jsCommonDataV1.webApi+'/gateway/uniform/basketball/getMatchCalculatorV1.qry?channel='+commonV1Fun.comDataChannel;
        }
        if(dataTransferClass.curSelectedGame != ''){
            apiurl += '&poolCode='+dataTransferClass.curSelectedGame
        }

        commonV1Fun.ajaxFun(
            dataTransferClass.formatToOld,
            apiurl,
            undefined,
            'get'
        )
    },
    //调用赔率变化接口
    getOddsHistoryDate: function (pool,id){
        commonV1Fun.ajaxFun(
            dataTransferClass.OddsHistoryToOld,
            jsCommonDataV1.webApi+'/gateway/uniform/football/getOddsHistoryV1.qry?matchId='+id+'&poolCode='+pool,
            undefined,
            'get'
        )
    },
    getBKOddsHistoryDate: function (pool,id){
        commonV1Fun.ajaxFun(
            dataTransferClass.bkOddsHistoryToOld,
            jsCommonDataV1.webApi+'/gateway/uniform/basketball/getOddsHistoryV1.qry?matchId='+id+'&poolCode='+pool,
            undefined,
            'get'
        )
    },
    //调用支持率接口
    getSupportDate: function (){
        commonV1Fun.ajaxFun(
            getReferData1,
            jsCommonDataV1.webApi+'/gateway/jc/common/getSupportRateV1.qry?matchIds='+dataTransferClass.matchIdList+'&poolCode=hhad,had&sportType='+dataTransferClass.curSportType,
            undefined,
            'get'
        )
    },
    //调用支持率采集接口
    collectSupportDate: function (mid, pool, value){
        var postData = {"matchId":mid,"poolCode":pool,"sportType":dataTransferClass.curSportType,"had":value};
        $.ajax({
            type: 'POST',
            url: jsCommonDataV1.webApi+'/gateway/jc/common/collectSupportRateV1.tran',
            data: JSON.stringify(postData),
            dataType: "json",
            headers: {"Content-type":"application/json;charset=utf-8"}
        });
    },
    formatToOld: function (data) {
        if (data.errorCode == 0 && JSON.stringify(data.value) != '{}') {
            if(dataTransferClass.curSelectedGame == ''){
                if(data.value.matchInfoList){
                    dataTransferClass.formatHhggToOld(data.value);
                }else{
                    getData();
                }
            }else{
                if(data.value.matchInfoList){
                    dataTransferClass.formatGamesToOld(data.value);
                }else{
                    getData();
                }
            }
        }else{
            getData();
        }
    },
    formatGamesToOld: function (data) {
            var oldDS = {"data" : {}, "status" : {"allup":{},"last_updated":data.lastUpdateTime}};
            if(dataTransferClass.curSelectedGame.indexOf("had") != -1){
                oldDS.status["maxcount"] = data.allUpList.HAD[0].maxMatchCount;
            }else{
                oldDS.status["maxcount"] = data.allUpList[dataTransferClass.curSelectedGame.toUpperCase()][0].maxMatchCount;
            }
            var tempMatchObj = { 
                "id": "", 
                "num": "", 
                "date": "", 
                "time": "", 
                "b_date": "", 
                "status": "", 
                "hot": "0", 
                "l_id": "", 
                "l_cn": "", 
                "h_id": "", 
                "h_cn": "", 
                "a_id": "", 
                "a_cn": "", 
                "index_show": "0", 
                "show": "1", 
                "l_cn_abbr": "", 
                "h_cn_abbr": "", 
                "a_cn_abbr": "", 
                "h_en_abbr": "", 
                "a_en_abbr": "", 
                "h_order": "", 
                "a_order": "", 
                "h_id_dc": "", 
                "a_id_dc": "", 
                "l_background_color": "", 
                "weather": "", 
                "weather_city": "", 
                "temperature": "", 
                "weather_pic": "", 
                "match_info": "",
                "match_num_date":"", // 比赛编号日期
                "tax_date_no":"" //计税期号
            };
            var newData = data.matchInfoList;
            var matchIdList = [];
            for (var i = 0; i < newData.length; i++) {
                var eleMatch = newData[i].subMatchList;
                for (var j = 0; j < eleMatch.length; j++) {
                    var ele = eleMatch[j];
                    matchIdList.push(ele.matchId);
                    tempMatchObj.id = ele.matchId;
                    tempMatchObj.num = ele.matchNumStr;
                    tempMatchObj.date = ele.matchDate;
                    tempMatchObj.time = ele.matchTime;
                    tempMatchObj.b_date = ele.businessDate; 
                    tempMatchObj.status = ele.matchStatus;
                    tempMatchObj.hot = ele.isHot;
                    tempMatchObj.l_id = ele.leagueId;
                    tempMatchObj.l_cn = ele.leagueAllName;
                    tempMatchObj.h_id = ele.homeTeamId;
                    tempMatchObj.h_cn = ele.homeTeamAllName;
                    tempMatchObj.a_id = ele.awayTeamId;
                    tempMatchObj.a_cn = ele.awayTeamAllName;
                    tempMatchObj.show = !ele.isHide;
                    tempMatchObj.l_cn_abbr = ele.leagueAbbName;
                    tempMatchObj.h_cn_abbr = ele.homeTeamAbbName;
                    tempMatchObj.a_cn_abbr = ele.awayTeamAbbName;
                    tempMatchObj.h_en_abbr = ele.homeTeamAbbEnName;
                    tempMatchObj.a_en_abbr = ele.awayTeamAbbEnName;
                    tempMatchObj.h_order = ele.homeRank;
                    tempMatchObj.a_order = ele.awayRank;
                    tempMatchObj.h_id_dc = ele.baseHomeTeamId;
                    tempMatchObj.a_id_dc = ele.baseAwayTeamId;
                    tempMatchObj.l_background_color = ele.backColor;
                    tempMatchObj.match_info = ele.remark;
                    tempMatchObj.match_num_date = ele.matchNumDate;// 比赛编号日期
                    tempMatchObj.tax_date_no = ele.taxDateNo //计税期号
                    if(JSON.stringify(ele.poolList) != "{}"){
                        tempMatchObj = dataTransferClass.getPoolListData(ele,tempMatchObj);
                    }
                                
                    oldDS.data["_"+ele.matchId] = JSON.parse(JSON.stringify(tempMatchObj));
                    tempMatchObj = {};
                }
            }

            dataTransferClass.matchIdList = matchIdList.join(',');
            //console.log(oldDS);
            getData(oldDS);
    },
    formatHhggToOld: function (d) {
        var max_count = d.lastUpdateTime;
        var allup = [];
        var newData = d.matchInfoList;
        for (var i = 0; i < newData.length; i++) {
            var eleMatch = newData[i].subMatchList;
            for (var j = 0; j < eleMatch.length; j++) {
                var ele = eleMatch[j];
                var matchArr = [];
                var matchListArr = [];
                if(dataTransferClass.curSportType == 1){
                    var hhadGoalLine = ele.hhad.goalLine?ele.hhad.goalLine:'0';
                    var hadGoalLine = ele.had.goalLine?ele.had.goalLine:'0';
                    var hadStr=this.getIsSelling(hadGoalLine,'had',ele.poolList);
                    var hhadStr=this.getIsSelling(hhadGoalLine,'hhad',ele.poolList);
                    //matchArr.push(ele.matchNumStr,ele.leagueAbbName,ele.homeTeamAbbName+'$'+hhadGoalLine+'$'+ele.awayTeamAbbName);
                    matchArr.push(ele.matchNumStr,ele.leagueAbbName,ele.homeTeamAbbName+'$'+hadStr+'*'+hhadStr+'$'+ele.awayTeamAbbName);
                }else{
                    matchArr.push(ele.matchNumStr,ele.leagueAbbName,ele.awayTeamAbbName,ele.homeTeamAbbName);
                }
                matchArr.push(ele.matchDate+' '+ele.matchTime.substring(0,5),ele.matchId.toString(),'#'+ele.backColor,ele.leagueAllName);
                if(dataTransferClass.curSportType == 1){
                    matchArr.push(ele.homeTeamAllName,ele.awayTeamAllName,ele.homeRank,ele.awayRank,ele.businessDate,ele.homeTeamId.toString(),ele.awayTeamId.toString(),ele.leagueId.toString(),ele.homeTeamAbbEnName,ele.awayTeamAbbEnName);
                }else{
                    matchArr.push(ele.awayTeamAllName,ele.homeTeamAllName,ele.awayRank,ele.homeRank,ele.businessDate,ele.awayTeamId.toString(),ele.homeTeamId.toString(),ele.leagueId.toString(),ele.awayTeamAbbEnName,ele.homeTeamAbbEnName);
                }
                matchArr.push(ele.matchNumDate, ele.taxDateNo)
                for (var m = 0; m < ele.poolList.length; m++) {
                    var eleGame = ele.poolList[m].poolCode.toLowerCase();
                    if(JSON.stringify(ele[eleGame]) != "{}"){
                        switch (eleGame) {
                            case 'hhad':
                                var hhadOdds = [];
                                hhadOdds.push(ele[eleGame].h,ele[eleGame].d,ele[eleGame].a,ele.poolList[m].cbtValue);
                                break;
                            case 'crs':
                                var crsOdds = [];
                                crsOdds.push(ele[eleGame].s01s00,ele[eleGame].s02s00,ele[eleGame].s02s01,ele[eleGame].s03s00,ele[eleGame].s03s01,ele[eleGame].s03s02,ele[eleGame].s04s00,ele[eleGame].s04s01,ele[eleGame].s04s02,ele[eleGame].s05s00,ele[eleGame].s05s01,ele[eleGame].s05s02,ele[eleGame].s1sh,ele[eleGame].s00s00,ele[eleGame].s01s01,ele[eleGame].s02s02,ele[eleGame].s03s03,ele[eleGame].s1sd,ele[eleGame].s00s01,ele[eleGame].s00s02,ele[eleGame].s01s02,ele[eleGame].s00s03,ele[eleGame].s01s03,ele[eleGame].s02s03,ele[eleGame].s00s04,ele[eleGame].s01s04,ele[eleGame].s02s04,ele[eleGame].s00s05,ele[eleGame].s01s05,ele[eleGame].s02s05,ele[eleGame].s1sa,ele.poolList[m].single,ele.poolList[m].cbtValue);
                                break;
                            case 'ttg':
                                var ttgOdds = [];
                                ttgOdds.push(ele[eleGame].s0,ele[eleGame].s1,ele[eleGame].s2,ele[eleGame].s3,ele[eleGame].s4,ele[eleGame].s5,ele[eleGame].s6,ele[eleGame].s7,ele.poolList[m].cbtValue);
                                break;
                            case 'hafu':
                                var hafuOdds = [];
                                hafuOdds.push(ele[eleGame].hh,ele[eleGame].hd,ele[eleGame].ha,ele[eleGame].dh,ele[eleGame].dd,ele[eleGame].da,ele[eleGame].ah,ele[eleGame].ad,ele[eleGame].aa,ele.poolList[m].cbtValue);
                                break;
                            case 'had':
                                var hadOdds = [];
                                hadOdds.push(ele[eleGame].h,ele[eleGame].d,ele[eleGame].a,ele.poolList[m].cbtValue);
                                break;
                            case 'hdc':
                                var hdcOdds = [];
                                hdcOdds.push(ele[eleGame].goalLine,ele[eleGame].a,ele[eleGame].h,ele.poolList[m].cbtValue);
                                break;
                            case 'hilo':
                                var hiloOdds = [];
                                hiloOdds.push(ele[eleGame].goalLine,ele[eleGame].h,ele[eleGame].l,ele.poolList[m].cbtValue);
                                break;
                            case 'mnl':
                                var mnlOdds = [];
                                mnlOdds.push(ele[eleGame].a,ele[eleGame].h,ele.poolList[m].cbtValue);
                                break;
                            case 'wnm':
                                var wnmOdds = [];
                                wnmOdds.push(ele[eleGame].l1,ele[eleGame].l2,ele[eleGame].l3,ele[eleGame].l4,ele[eleGame].l5,ele[eleGame].l6,ele[eleGame].w1,ele[eleGame].w2,ele[eleGame].w3,ele[eleGame].w4,ele[eleGame].w5,ele[eleGame].w6,ele.poolList[m].single,ele.poolList[m].cbtValue);
                                break;
                            default:
                                break;
                        }
                    }
                }
                matchListArr.push(matchArr);
                if(dataTransferClass.curSportType == 1){
                    if(hhadOdds && hhadOdds.length > 0){
                        matchListArr.push(hhadOdds);
                        hhadOdds = [];
                    }else{
                        matchListArr.push(["","","","0"]);
                    }
                    if(crsOdds && crsOdds.length > 0){
                        matchListArr.push(crsOdds);
                        crsOdds = [];
                    }else{
                        matchListArr.push(["","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","","0"]);
                    }
                    if(ttgOdds && ttgOdds.length > 0){
                        matchListArr.push(ttgOdds);
                        ttgOdds = [];
                    }else{
                        matchListArr.push(["","","","","","","","","0"]);
                    }
                    if(hafuOdds && hafuOdds.length > 0){
                        matchListArr.push(hafuOdds);
                        hafuOdds = [];
                    }else{
                        matchListArr.push(["","","","","","","","","","0"]);
                    }
                    if(hadOdds && hadOdds.length > 0){
                        matchListArr.push(hadOdds);
                        hadOdds = [];
                    }else{
                        matchListArr.push(["","","","0"]);
                    } 
                }else{
                    if(mnlOdds && mnlOdds.length > 0){
                        matchListArr.push(mnlOdds);
                        mnlOdds = [];
                    }else{
                        matchListArr.push(["","","0"]);
                    } 
                    if(hdcOdds && hdcOdds.length > 0){
                        matchListArr.push(hdcOdds);
                        hdcOdds = [];
                    }else{
                        matchListArr.push(["","","","0"]);
                    } 
                    if(hiloOdds && hiloOdds.length > 0){
                        matchListArr.push(hiloOdds);
                        hiloOdds = [];
                    }else{
                        matchListArr.push(["","","","0"]);
                    } 
                    if(wnmOdds && wnmOdds.length > 0){
                        matchListArr.push(wnmOdds);
                        wnmOdds = [];
                    }else{
                        matchListArr.push(["","","","","","","","","","","","","0","0"]);
                    } 
                }
                data.push(matchListArr);
            }
        }
        getData();
    },
    getIsSelling:function(goalLine, game,poolList){
        var sellingStatus="--";
        for (var m = 0; m < poolList.length; m++) {
            var eleGame = poolList[m].poolCode.toLowerCase();
            if(JSON.stringify(poolList[eleGame]) != "{}"){
                if(game == eleGame &&(eleGame == 'hhad' || eleGame =='had' || eleGame =="hdc" || eleGame == "mnl")){
                    sellingStatus = goalLine;
                    break;
                }
            }
        }
        return sellingStatus;
    },
    getPoolListData: function (pData,tempMatchObj) {
        for (var n = 0; n < pData.poolList.length; n++) {
            var plele = pData.poolList[n];
            var sellingPoolName = plele.poolCode.toLowerCase();
            var tempPoolObj = {};
            tempPoolObj['p_code'] = plele.poolCode;
            tempPoolObj['o_type'] = plele.poolOddsType;
            tempPoolObj['p_id'] = plele.poolId;
            tempPoolObj['p_status'] = plele.poolStatus;
            tempPoolObj['single'] = plele.single;
            tempPoolObj['allup'] = plele.allUp;
            tempPoolObj['cbt'] = plele.cbtValue;
            tempPoolObj['int'] = plele.intValue;
            tempPoolObj['vbt'] = plele.vbtValue;
            tempPoolObj = dataTransferClass.getOddsData(pData[sellingPoolName],sellingPoolName,tempPoolObj);
            tempMatchObj[sellingPoolName] = tempPoolObj;
        }
        return tempMatchObj;
    },
    getOddsData: function (oData,t,tempHadObj) {
        switch (t) {
            case 'crs':
                tempHadObj['-1-a'] = oData.s1sa?oData.s1sa:'';
                tempHadObj['-1-d'] = oData.s1sd?oData.s1sd:'';
                tempHadObj['-1-h'] = oData.s1sh?oData.s1sh:'';
                tempHadObj['0000'] = oData.s00s00?oData.s00s00:'';
                tempHadObj['0001'] = oData.s00s01?oData.s00s01:'';
                tempHadObj['0002'] = oData.s00s02?oData.s00s02:'';
                tempHadObj['0003'] = oData.s00s03?oData.s00s03:'';
                tempHadObj['0004'] = oData.s00s04?oData.s00s04:'';
                tempHadObj['0005'] = oData.s00s05?oData.s00s05:'';
                tempHadObj['0100'] = oData.s01s00?oData.s01s00:'';
                tempHadObj['0101'] = oData.s01s01?oData.s01s01:'';
                tempHadObj['0102'] = oData.s01s02?oData.s01s02:'';
                tempHadObj['0103'] = oData.s01s03?oData.s01s03:'';
                tempHadObj['0104'] = oData.s01s04?oData.s01s04:'';
                tempHadObj['0105'] = oData.s01s05?oData.s01s05:'';
                tempHadObj['0200'] = oData.s02s00?oData.s02s00:'';
                tempHadObj['0201'] = oData.s02s01?oData.s02s01:'';
                tempHadObj['0202'] = oData.s02s02?oData.s02s02:'';
                tempHadObj['0203'] = oData.s02s03?oData.s02s03:'';
                tempHadObj['0204'] = oData.s02s04?oData.s02s04:'';
                tempHadObj['0205'] = oData.s02s05?oData.s02s05:'';
                tempHadObj['0300'] = oData.s03s00?oData.s03s00:'';
                tempHadObj['0301'] = oData.s03s01?oData.s03s01:'';
                tempHadObj['0302'] = oData.s03s02?oData.s03s02:'';
                tempHadObj['0303'] = oData.s03s03?oData.s03s03:'';
                tempHadObj['0400'] = oData.s04s00?oData.s04s00:'';
                tempHadObj['0401'] = oData.s04s01?oData.s04s01:'';
                tempHadObj['0402'] = oData.s04s02?oData.s04s02:'';
                tempHadObj['0500'] = oData.s05s00?oData.s05s00:'';
                tempHadObj['0501'] = oData.s05s01?oData.s05s01:'';
                tempHadObj['0502'] = oData.s05s02?oData.s05s02:'';
                break;
            case 'ttg':
                tempHadObj['s0'] = oData.s0?oData.s0:'';
                tempHadObj['s1'] = oData.s1?oData.s1:'';
                tempHadObj['s2'] = oData.s2?oData.s2:'';
                tempHadObj['s3'] = oData.s3?oData.s3:'';
                tempHadObj['s4'] = oData.s4?oData.s4:'';
                tempHadObj['s5'] = oData.s5?oData.s5:'';
                tempHadObj['s6'] = oData.s6?oData.s6:'';
                tempHadObj['s7'] = oData.s7?oData.s7:'';
                break;
            case 'hafu':
                tempHadObj['aa'] = oData.aa?oData.aa:'';
                tempHadObj['ad'] = oData.ad?oData.ad:'';
                tempHadObj['ah'] = oData.ah?oData.ah:'';
                tempHadObj['da'] = oData.da?oData.da:'';
                tempHadObj['dd'] = oData.dd?oData.dd:'';
                tempHadObj['dh'] = oData.dh?oData.dh:'';
                tempHadObj['ha'] = oData.ha?oData.ha:'';
                tempHadObj['hd'] = oData.hd?oData.hd:'';
                tempHadObj['hh'] = oData.hh?oData.hh:'';
                break;
            case 'mnl':
                tempHadObj['a'] = oData.a?oData.a:'';
                tempHadObj['h'] = oData.h?oData.h:'';
                tempHadObj['h_trend'] = oData.hf?oData.hf:'';
                tempHadObj['a_trend'] = oData.af?oData.af:'';
                break;
            case 'hdc':
                tempHadObj['a'] = oData.a?oData.a:'';
                tempHadObj['h'] = oData.h?oData.h:'';
                tempHadObj['h_trend'] = oData.hf?oData.hf:'';
                tempHadObj['a_trend'] = oData.af?oData.af:'';
                break;
            case 'wnm':
                tempHadObj['l1'] = oData.l1?oData.l1:'';
                tempHadObj['l2'] = oData.l2?oData.l2:'';
                tempHadObj['l3'] = oData.l3?oData.l3:'';
                tempHadObj['l4'] = oData.l4?oData.l4:'';
                tempHadObj['l5'] = oData.l5?oData.l5:'';
                tempHadObj['l6'] = oData.l6?oData.l6:'';
                tempHadObj['w1'] = oData.w1?oData.w1:'';
                tempHadObj['w2'] = oData.w2?oData.w2:'';
                tempHadObj['w3'] = oData.w3?oData.w3:'';
                tempHadObj['w4'] = oData.w4?oData.w4:'';
                tempHadObj['w5'] = oData.w5?oData.w5:'';
                tempHadObj['w6'] = oData.w6?oData.w6:'';
                break;
            case 'hilo':
                tempHadObj['l'] = oData.l?oData.l:'';
                tempHadObj['h'] = oData.h?oData.h:'';
                tempHadObj['h_trend'] = oData.hf?oData.hf:'';
                tempHadObj['l_trend'] = oData.lf?oData.lf:'';
                break;
            default:
                tempHadObj['a'] = oData.a?oData.a:'';
                tempHadObj['d'] = oData.d?oData.d:'';
                tempHadObj['h'] = oData.h?oData.h:'';
                tempHadObj['h_trend'] = oData.hf?oData.hf:'';
                tempHadObj['a_trend'] = oData.af?oData.af:'';
                tempHadObj['d_trend'] = oData.df?oData.df:'';
                break;
        }
        tempHadObj['fixedodds'] = oData.goalLine;

        return tempHadObj;
    },
    OddsHistoryToOld: function (ohData) {
        if (ohData.errorCode == 0) {
            if(ohData.value.hadList.length > 0){
                var ohHadList = ohData.value.hadList;
            }else if(ohData.value.hhadList.length > 0){
                var ohHadList = ohData.value.hhadList;
            }
            var ohHadHtml = '';
            if(ohHadList){
                ohHadHtml = '<div class="OpenDivTop"><table class="OpenDivMain" cellpadding="0" cellspacing="0"><tr bgcolor="#F0F8FF"><td>胜</td><td>平</td><td>负</td><td>时间</td></tr>';

                for (var i = 0; i < ohHadList.length; i++) {
                    var oddLine = ohHadList[i];
                    ohHadHtml += '<tr>';
                    if(oddLine.hf == '1'){
                        ohHadHtml += '<td><font color="#FF0000">'+oddLine.h+'↑</font></td>';
                    }else if(oddLine.hf == '-1'){
                        ohHadHtml += '<td><font color="#269803">'+oddLine.h+'↓</font></td>';
                    }else{
                        ohHadHtml += '<td>'+oddLine.h+'</td>';
                    }
                    if(oddLine.df == '1'){
                        ohHadHtml += '<td><font color="#FF0000">'+oddLine.d+'↑</font></td>';
                    }else if(oddLine.df == '-1'){
                        ohHadHtml += '<td><font color="#269803">'+oddLine.d+'↓</font></td>';
                    }else{
                        ohHadHtml += '<td>'+oddLine.d+'</td>';
                    }
                    if(oddLine.af == '1'){
                        ohHadHtml += '<td><font color="#FF0000">'+oddLine.a+'↑</font></td>';
                    }else if(oddLine.af == '-1'){
                        ohHadHtml += '<td><font color="#269803">'+oddLine.a+'↓</font></td>';
                    }else{
                        ohHadHtml += '<td>'+oddLine.a+'</td>';
                    }
                    ohHadHtml += '<td>'+oddLine.updateDate.substring(5)+' '+oddLine.updateTime.substring(0,5)+'</td></tr>';
                }
                ohHadHtml += '</table></div>';
                getChgData(ohHadHtml);
            }
        }
    },
    bkOddsHistoryToOld: function (bkohData) {
        if (bkohData.errorCode == 0) {
            var bkohHtml = '';
            if(bkohData.value.mnlList.length > 0){
                bkohHtml = dataTransferClass.getMnlHistoryHtml(bkohData.value.mnlList);
            }else if(bkohData.value.hdcList.length > 0){
                bkohHtml = dataTransferClass.getHdcHistoryHtml(bkohData.value.hdcList);
            }else if(bkohData.value.hiloList.length > 0){
                bkohHtml = dataTransferClass.getHiloHistoryHtml(bkohData.value.hiloList);
            }
            getChgData(bkohHtml);
        }
    },
    getMnlHistoryHtml: function (mData) {
        var ohHtml = '<div class="OpenDivTop"><table class="OpenDivMain" cellpadding="0" cellspacing="0"><tr bgcolor="#F0F8FF"><td>主负</td><td>主胜</td><td>时间</td></tr>';

        for (var i = 0; i < mData.length; i++) {
            var oddLine = mData[i];
            ohHtml += '<tr>';
            if(oddLine.af == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.a+'↑</font></td>';
            }else if(oddLine.af == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.a+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.a+'</td>';
            }
            if(oddLine.hf == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.h+'↑</font></td>';
            }else if(oddLine.hf == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.h+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.h+'</td>';
            }
            ohHtml += '<td>'+oddLine.updateDate.substring(5)+' '+oddLine.updateTime.substring(0,5)+'</td></tr>';
        }
        ohHtml += '</table></div>';
        return ohHtml;
    },
    getHdcHistoryHtml: function (mData) {
        var ohHtml = '<div class="OpenDivTop"><table class="OpenDivMain" cellpadding="0" cellspacing="0"><tr bgcolor="#F0F8FF"><td>让分主负</td><td>让分</td><td>让分主胜</td><td>时间</td></tr>';

        for (var i = 0; i < mData.length; i++) {
            var oddLine = mData[i];
            ohHtml += '<tr>';
            if(oddLine.af == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.a+'↑</font></td>';
            }else if(oddLine.af == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.a+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.a+'</td>';
            }
            if(oddLine.goalLinef == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.goalLine+'↑</font></td>';
            }else if(oddLine.goalLinef == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.goalLine+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.goalLine+'</td>';
            }
            if(oddLine.hf == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.h+'↑</font></td>';
            }else if(oddLine.hf == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.h+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.h+'</td>';
            }
            ohHtml += '<td>'+oddLine.updateDate.substring(5)+' '+oddLine.updateTime.substring(0,5)+'</td></tr>';
        }
        ohHtml += '</table></div>';
        return ohHtml;
    },
    getHiloHistoryHtml: function (mData) {
        var ohHtml = '<div class="OpenDivTop"><table class="OpenDivMain" cellpadding="0" cellspacing="0"><tr bgcolor="#F0F8FF"><td>大分</td><td>总分</td><td>小分</td><td>时间</td></tr>';

        for (var i = 0; i < mData.length; i++) {
            var oddLine = mData[i];
            ohHtml += '<tr>';
            if(oddLine.hf == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.h+'↑</font></td>';
            }else if(oddLine.hf == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.h+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.h+'</td>';
            }
            if(oddLine.goalLinef == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.goalLine+'↑</font></td>';
            }else if(oddLine.goalLinef == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.goalLine+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.goalLine+'</td>';
            }
            if(oddLine.lf == '1'){
                ohHtml += '<td><font color="#FF0000">'+oddLine.l+'↑</font></td>';
            }else if(oddLine.lf == '-1'){
                ohHtml += '<td><font color="#269803">'+oddLine.l+'↓</font></td>';
            }else{
                ohHtml += '<td>'+oddLine.l+'</td>';
            }
            ohHtml += '<td>'+oddLine.updateDate.substring(5)+' '+oddLine.updateTime.substring(0,5)+'</td></tr>';
        }
        ohHtml += '</table></div>';
        return ohHtml;
    }


}