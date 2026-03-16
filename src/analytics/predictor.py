import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error
from datetime import datetime, timedelta
import joblib
import os
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

from ..utils.config import ML_CONFIG
from .feature_engineering import FeatureEngineer

class PricePredictor:
    """
    AI Price Predictor using Random Forest Regression.
    Predicts future close prices based on technical indicators.
    Each stock gets its own trained model.
    """

    def __init__(self):
        pred_config = ML_CONFIG.get("prediction", {})
        self.n_estimators = pred_config.get("n_estimators", 100)
        self.random_state = pred_config.get("random_state", 42)
        
        self.model = RandomForestRegressor(n_estimators=self.n_estimators, random_state=self.random_state)
        self.scaler = StandardScaler()
        self.is_trained = False
        self.trained_symbol = None  # Track which symbol the model was trained for
        self.model_metrics = {}  # Store performance metrics (MAE, RMSE, direction accuracy)
        self.feature_columns = [
            'returns', 'log_returns', 'high_low_pct', 'close_sma5_ratio',
            'close_sma20_ratio', 'rsi', 'volatility', 'volume_ratio'
        ]
        self.model_path = os.path.join(os.path.dirname(__file__), "model_data")
        os.makedirs(self.model_path, exist_ok=True)

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer relative/normalized features for the model.
        Uses returns and ratios instead of absolute prices to avoid
        sensitivity to price level changes.
        """
        data = df.copy()
        
        # Returns-based features (price-level independent)
        data['returns'] = data['close'].pct_change()
        data['log_returns'] = np.log(data['close'] / data['close'].shift(1))
        
        # Relative range (high-low as % of close)
        data['high_low_pct'] = (data['high'] - data['low']) / data['close']
        
        # Price relative to moving averages (ratio form)
        sma_5 = data['close'].rolling(window=5).mean()
        sma_20 = data['close'].rolling(window=20).mean()
        data['close_sma5_ratio'] = data['close'] / sma_5
        data['close_sma20_ratio'] = data['close'] / sma_20
        
        # RSI (already 0-100 scale, price-independent)
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        data['rsi'] = 100 - (100 / (1 + rs))
        
        # Volatility (std of returns, price-independent)
        data['volatility'] = data['returns'].rolling(window=20).std()
        
        # Volume ratio (relative to 20-day average)
        vol_ma20 = data['volume'].rolling(window=20).mean()
        data['volume_ratio'] = data['volume'] / (vol_ma20 + 1e-10)
        
        # Target: next-day return
        data['next_return'] = data['returns'].shift(-1)
        
        # Drop NaN created by rolling windows
        data = data.dropna(subset=self.feature_columns)
        
        return data

    def save_model(self, symbol: str):
        """Save trained model and scaler to disk for a specific symbol"""
        try:
            safe_symbol = symbol.replace("/", "_").replace("\\", "_")
            model_file = os.path.join(self.model_path, f"rf_model_{safe_symbol}.joblib")
            scaler_file = os.path.join(self.model_path, f"scaler_{safe_symbol}.joblib")
            joblib.dump(self.model, model_file)
            joblib.dump(self.scaler, scaler_file)
            logger.info(f"Model saved successfully for {symbol}")
        except Exception as e:
            logger.error(f"Failed to save model for {symbol}: {e}")

    def load_model(self, symbol: str) -> bool:
        """Load trained model and scaler from disk for a specific symbol"""
        try:
            safe_symbol = symbol.replace("/", "_").replace("\\", "_")
            model_file = os.path.join(self.model_path, f"rf_model_{safe_symbol}.joblib")
            scaler_file = os.path.join(self.model_path, f"scaler_{safe_symbol}.joblib")
            
            if os.path.exists(model_file) and os.path.exists(scaler_file):
                self.model = joblib.load(model_file)
                self.scaler = joblib.load(scaler_file)
                self.is_trained = True
                self.trained_symbol = symbol
                logger.info(f"Model loaded successfully for {symbol}")
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to load model for {symbol} (will need retraining): {e}")
            return False

    def _is_model_stale(self) -> bool:
        """Check if the trained model is older than 24 hours."""
        if not self.model_metrics:
            return True
        trained_at = self.model_metrics.get("trained_at")
        if not trained_at:
            return True
        try:
            trained_time = datetime.fromisoformat(trained_at)
            return (datetime.now() - trained_time).total_seconds() > 86400  # 24h
        except Exception:
            return True

    def train(self, historical_data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """
        Train the model on historical data for a specific symbol.
        Predicts next-day RETURN (not absolute price) to be price-level independent.
        """
        try:
            if len(historical_data) < 50:
                raise ValueError("Insufficient data points for training (min 50 required)")

            # Create fresh model and scaler for this symbol
            self.model = RandomForestRegressor(n_estimators=self.n_estimators, random_state=self.random_state)
            self.scaler = StandardScaler()

            df_features = self._prepare_features(historical_data)
            
            # Target: next-day return (already computed in _prepare_features)
            valid = df_features.dropna(subset=['next_return'])
            X = valid[self.feature_columns]
            y = valid['next_return']  # Predict next-day return
            
            if len(X) < 50:
                raise ValueError(f"Insufficient valid samples after feature engineering: {len(X)}")
            
            # Split data for evaluation (80% train, 20% test)
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, shuffle=False  # Keep temporal order
            )
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train model
            self.model.fit(X_train_scaled, y_train)
            
            # Evaluate on test set
            y_pred = self.model.predict(X_test_scaled)
            
            # Calculate metrics
            mae = mean_absolute_error(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            
            # Direction accuracy
            actual_direction = np.sign(y_test.values)
            pred_direction = np.sign(y_pred)
            direction_accuracy = np.mean(actual_direction == pred_direction) * 100
            
            # Store metrics
            self.model_metrics = {
                "mae": round(mae, 6),
                "rmse": round(rmse, 6),
                "direction_accuracy": round(direction_accuracy, 2),
                "train_samples": len(X_train),
                "test_samples": len(X_test),
                "trained_at": datetime.now().isoformat()
            }
            
            # Retrain on full data for production use
            X_all_scaled = self.scaler.fit_transform(X)
            self.model.fit(X_all_scaled, y)
            
            self.is_trained = True
            self.trained_symbol = symbol
            self.save_model(symbol)
            logger.info(f"PricePredictor trained for {symbol}: MAE={mae:.6f}, RMSE={rmse:.6f}, Direction Acc={direction_accuracy:.2f}%")
            
            return self.model_metrics
            
        except Exception as e:
            logger.error(f"Error training prediction model for {symbol}: {e}")
            raise

    def predict_next_days(self, current_data: pd.DataFrame, days: int = 5, symbol: str = "UNKNOWN") -> Dict[str, Any]:
        """
        Predict prices for the next 'days' days using recursive prediction.
        Predicts next-day returns, then converts to absolute prices.
        """
        # Check if we need to train/load a model for this symbol
        needs_training = (
            not self.is_trained 
            or self.trained_symbol != symbol 
            or self._is_model_stale()
        )
        if needs_training:
            # Try to load existing model for this symbol
            loaded = self.load_model(symbol)
            if not loaded or self._is_model_stale():
                self.train(current_data, symbol)

        try:
            simulation_df = current_data.copy()
            
            predictions = []
            confidence_intervals = []
            dates = []
            
            last_date = simulation_df.index[-1]
            if not isinstance(last_date, pd.Timestamp):
                last_date = pd.to_datetime(last_date)

            # Current price is the anchor for converting returns → prices  
            current_price = float(simulation_df['close'].iloc[-1])

            # Get model uncertainty from tree variance
            df_features_init = self._prepare_features(simulation_df)
            if len(df_features_init) == 0:
                raise ValueError("Feature preparation produced no valid rows")
            last_features_init = df_features_init.iloc[-1][self.feature_columns].values.reshape(1, -1)
            scaled_input_init = self.scaler.transform(last_features_init)
            returns_all_trees = np.array([tree.predict(scaled_input_init)[0] for tree in self.model.estimators_])
            base_return_std = np.std(returns_all_trees)

            running_price = current_price
            
            for i in range(days):
                # 1. Prepare features from simulation data
                df_features = self._prepare_features(simulation_df)
                
                # 2. Get the last row of features
                last_features = df_features.iloc[-1][self.feature_columns].values.reshape(1, -1)
                
                # 3. Scale and predict next-day RETURN
                scaled_input = self.scaler.transform(last_features)
                predicted_return = self.model.predict(scaled_input)[0]
                
                # 4. Convert return to price
                next_price = running_price * (1 + predicted_return)
                next_price = round(next_price, 2)
                predictions.append(next_price)
                running_price = next_price
                
                # 5. Confidence interval (return std → price std)
                uncertainty_factor = 1.0 + (i * 0.2)
                return_ci = base_return_std * uncertainty_factor * 1.96
                price_ci = next_price * return_ci
                
                confidence_intervals.append({
                    "upper": round(next_price + price_ci, 2),
                    "lower": round(next_price - price_ci, 2)
                })
                
                next_date = last_date + timedelta(days=i+1)
                dates.append(next_date.isoformat())
                
                # 6. Append predicted row for next iteration's rolling features
                new_row = pd.Series(index=simulation_df.columns, dtype=float)
                new_row['close'] = next_price
                new_row['high'] = next_price * 1.005
                new_row['low'] = next_price * 0.995
                last_5_vol = simulation_df['volume'].tail(5).mean()
                new_row['volume'] = last_5_vol
                
                new_df_row = pd.DataFrame([new_row], index=[next_date])
                simulation_df = pd.concat([simulation_df, new_df_row])
                
            # Summary
            first_price = predictions[0]
            last_price = predictions[-1]
            price_change = last_price - first_price
            price_change_pct = (price_change / first_price) * 100 if first_price > 0 else 0
            
            if price_change_pct > 1.0:
                trend, trend_cn = "bullish", "看涨"
            elif price_change_pct < -1.0:
                trend, trend_cn = "bearish", "看跌"
            else:
                trend, trend_cn = "neutral", "震荡"
            
            # Confidence score based on direction accuracy
            confidence_score = 65
            if self.model_metrics:
                dir_acc = self.model_metrics.get("direction_accuracy", 50)
                if dir_acc > 55:
                    confidence_score += 15
                elif dir_acc > 50:
                    confidence_score += 5
            
            return {
                "dates": dates,
                "predicted_prices": predictions,
                "confidence_intervals": confidence_intervals,
                "currency": "USD",
                "prediction_summary": {
                    "trend": trend,
                    "trend_cn": trend_cn,
                    "price_change": round(price_change, 2),
                    "price_change_pct": round(price_change_pct, 2),
                    "starting_price": first_price,
                    "ending_price": last_price,
                    "confidence_score": round(confidence_score, 1)
                },
                "model_metrics": self.model_metrics if self.model_metrics else None
            }

        except Exception as e:
            logger.error(f"Error making prediction: {e}")
            raise
