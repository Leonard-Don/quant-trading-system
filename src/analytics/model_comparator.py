"""
模型比较服务
支持多种预测模型的对比分析
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging
from datetime import datetime

from .predictor import PricePredictor
from .lstm_predictor import lstm_predictor, TF_AVAILABLE

logger = logging.getLogger(__name__)


class ModelComparator:
    """
    模型比较器
    支持 Random Forest 和 LSTM 模型的对比
    """
    
    def __init__(self):
        self.rf_predictor = PricePredictor()
        self.lstm_predictor = lstm_predictor
        
    def get_available_models(self) -> List[Dict]:
        """获取可用的模型列表"""
        models = [
            {
                'id': 'random_forest',
                'name': 'Random Forest',
                'description': '随机森林回归模型，基于技术指标特征',
                'available': True
            },
            {
                'id': 'lstm',
                'name': 'LSTM',
                'description': '双向 LSTM 神经网络，捕捉时序依赖',
                'available': TF_AVAILABLE
            }
        ]
        return models
    
    def train_all_models(self, historical_data: pd.DataFrame, symbol: str) -> Dict:
        """
        训练所有可用模型
        
        Args:
            historical_data: 历史数据
            symbol: 股票代码
            
        Returns:
            各模型训练指标
        """
        results = {
            'symbol': symbol,
            'models': {}
        }
        
        # 训练 Random Forest
        try:
            rf_metrics = self.rf_predictor.train(historical_data, symbol)
            results['models']['random_forest'] = {
                'status': 'success',
                'metrics': rf_metrics
            }
        except Exception as e:
            logger.error(f"Error training Random Forest for {symbol}: {e}")
            results['models']['random_forest'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 训练 LSTM
        try:
            lstm_metrics = self.lstm_predictor.train(historical_data, symbol)
            results['models']['lstm'] = {
                'status': 'success',
                'metrics': lstm_metrics
            }
        except Exception as e:
            logger.error(f"Error training LSTM for {symbol}: {e}")
            results['models']['lstm'] = {
                'status': 'error',
                'error': str(e)
            }
        
        return results
    
    def predict_with_model(
        self, 
        current_data: pd.DataFrame, 
        symbol: str, 
        model_type: str = 'random_forest',
        days: int = 5
    ) -> Dict:
        """
        使用指定模型进行预测
        
        Args:
            current_data: 当前数据
            symbol: 股票代码
            model_type: 模型类型 ('random_forest' 或 'lstm')
            days: 预测天数
            
        Returns:
            预测结果
        """
        if model_type == 'lstm':
            return self.lstm_predictor.predict(current_data, symbol, days)
        else:
            return self.rf_predictor.predict_next_days(current_data, days, symbol)
    
    def compare_predictions(
        self, 
        current_data: pd.DataFrame, 
        symbol: str, 
        days: int = 5
    ) -> Dict:
        """
        比较不同模型的预测结果
        
        Args:
            current_data: 当前数据
            symbol: 股票代码
            days: 预测天数
            
        Returns:
            各模型预测结果对比
        """
        results = {
            'symbol': symbol,
            'forecast_days': days,
            'generated_at': datetime.now().isoformat(),
            'predictions': {}
        }
        
        # Random Forest 预测
        try:
            rf_pred = self.rf_predictor.predict_next_days(current_data, days, symbol)
            results['predictions']['random_forest'] = {
                'status': 'success',
                'model_name': 'Random Forest',
                **rf_pred
            }
        except Exception as e:
            logger.error(f"RF prediction error for {symbol}: {e}")
            results['predictions']['random_forest'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # LSTM 预测
        try:
            lstm_pred = self.lstm_predictor.predict(current_data, symbol, days)
            results['predictions']['lstm'] = {
                'status': 'success',
                'model_name': 'LSTM',
                **lstm_pred
            }
        except Exception as e:
            logger.error(f"LSTM prediction error for {symbol}: {e}")
            results['predictions']['lstm'] = {
                'status': 'error',
                'error': str(e)
            }
            
        # Extract dates from any successful prediction to top level
        # This ensures frontend compatibility (AIPredictionPanel.js expects data.dates)
        if 'random_forest' in results['predictions'] and 'dates' in results['predictions']['random_forest']:
             results['dates'] = results['predictions']['random_forest']['dates']
        elif 'lstm' in results['predictions'] and 'dates' in results['predictions']['lstm']:
             results['dates'] = results['predictions']['lstm']['dates']
        
        # 计算统计对比
        results['comparison'] = self._compute_comparison(results['predictions'])
        
        # Clean NaNs to ensure JSON compatibility
        return self._clean_nans(results)

    def _clean_nans(self, obj):
        """Recursively replace NaNs with None for JSON serialization"""
        if isinstance(obj, dict):
            return {k: self._clean_nans(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_nans(v) for v in obj]
        elif isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return obj
        elif isinstance(obj, np.generic):
            # Handle numpy scalars
            if np.isnan(obj) or np.isinf(obj):
                return None
            return obj.item()
        return obj
    
    def _compute_comparison(self, predictions: Dict) -> Dict:
        """计算模型预测对比统计"""
        comparison = {
            'models_compared': list(predictions.keys()),
            'agreement_metrics': {}
        }
        
        try:
            rf_prices = predictions.get('random_forest', {}).get('predicted_prices', [])
            lstm_prices = predictions.get('lstm', {}).get('predicted_prices', [])
            
            if rf_prices and lstm_prices:
                # 转换为 numpy 数组
                rf_arr = np.array(rf_prices)
                lstm_arr = np.array(lstm_prices)
                
                # 计算平均预测
                avg_prices = (rf_arr + lstm_arr) / 2
                
                # 计算模型差异
                diff = np.abs(rf_arr - lstm_arr)
                
                comparison['agreement_metrics'] = {
                    'mean_difference': float(np.mean(diff)),
                    'max_difference': float(np.max(diff)),
                    'mean_difference_percent': float(np.mean(diff / avg_prices) * 100),
                    'correlation': float(np.corrcoef(rf_arr, lstm_arr)[0, 1]) if len(rf_arr) > 1 else 1.0
                }
                
                # 趋势一致性
                rf_trend = 'up' if rf_arr[-1] > rf_arr[0] else 'down'
                lstm_trend = 'up' if lstm_arr[-1] > lstm_arr[0] else 'down'
                comparison['trend_agreement'] = rf_trend == lstm_trend
                
                # 集成预测（平均）
                comparison['ensemble_prediction'] = {
                    'predicted_prices': [float(p) for p in avg_prices],
                    'method': 'simple_average'
                }
                
        except Exception as e:
            logger.error(f"Error computing comparison: {e}")
            comparison['error'] = str(e)
        
        return comparison


# 全局实例
model_comparator = ModelComparator()
