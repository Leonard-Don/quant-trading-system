from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
import yfinance as yf
from datetime import datetime, timedelta
import logging
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

class EventRequest(BaseModel):
    symbol: str

@router.post("/summary", summary="获取股票相关事件")
async def get_events_summary(request: EventRequest):
    """
    获取股票的事件信息，包括财报、分红和新闻
    """
    try:
        ticker = yf.Ticker(request.symbol)
        
        # 1. 获取财报日历
        calendar = {}
        try:
            cal = ticker.calendar
            if cal is not None and not cal.empty:
                # yfinance calendar 格式可能不同，尝试通用获取
                next_earnings = cal.get('Earnings Date')
                if next_earnings is not None:
                     # 如果是 list，取第一个
                    if isinstance(next_earnings, list):
                        calendar['next_earnings'] = str(next_earnings[0])
                    else:
                        calendar['next_earnings'] = str(next_earnings)
                
                earnings_high = cal.get('Earnings High')
                earnings_low = cal.get('Earnings Low')
                earnings_avg = cal.get('Earnings Average')
                
                if earnings_avg is not None:
                    calendar['estimate_avg'] = float(earnings_avg) if hasattr(earnings_avg, '__float__') else str(earnings_avg)
        except Exception as e:
            logger.warning(f"获取财报日历失败: {e}")
            
        # 2. 获取分红信息
        dividends = {}
        try:
            # 获取最近的分红
            divs = ticker.dividends
            if not divs.empty:
                last_div_date = divs.index[-1]
                last_div_amount = divs.iloc[-1]
                dividends['last_date'] = last_div_date.strftime('%Y-%m-%d')
                dividends['last_amount'] = float(last_div_amount)
                
                # 简单预测下一次分红 (假设季度分红)
                next_div_date = last_div_date + timedelta(days=90)
                if next_div_date > datetime.now():
                    dividends['next_date_estimated'] = next_div_date.strftime('%Y-%m-%d')
        except Exception as e:
             logger.warning(f"获取分红信息失败: {e}")

        # 3. 获取新闻
        news = []
        try:
            # yfinance news
            yf_news = ticker.news
            if yf_news:
                for n in yf_news[:5]: # 只取前5条
                    news.append({
                        "title": n.get('title'),
                        "publisher": n.get('publisher'),
                        "link": n.get('link'),
                        "providerPublishTime": n.get('providerPublishTime'),
                        "type": n.get('type')
                    })
        except Exception as e:
             logger.warning(f"获取新闻失败: {e}")

        return {
            "symbol": request.symbol,
            "earnings": calendar,
            "dividends": dividends,
            "news": news
        }

    except Exception as e:
        logger.error(f"Error getting events summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
