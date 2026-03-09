#!/usr/bin/env python3
"""
Regime Detector - ML-based Market Regime Detection
Stub implementation for basic functionality
"""

from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum


class MarketRegime(Enum):
    """Market regime types"""
    BULL_STRONG = "bull_strong"
    BULL_MOD = "bull_moderate"
    SIDEWAYS = "sideways"
    BEAR_MOD = "bear_moderate"
    BEAR_STRONG = "bear_strong"
    UNKNOWN = "unknown"


import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

class RegimeDetector:
    """
    RandomForest-powered market regime detector
    """
    
    def __init__(self):
        self.current_regime = MarketRegime.UNKNOWN
        self.regime_confidence = 0.0
        self.price_history: List[Dict] = []
        
        self.model = None
        self._load_model()
        
    def _load_model(self):
        models_dir = Path(__file__).parent / 'models'
        pkl_path = models_dir / 'random_forest.pkl'
        if pkl_path.exists():
            try:
                with open(pkl_path, 'rb') as f:
                    self.model = pickle.load(f)
                print(f"✅ RegimeDetector: Successfully loaded {pkl_path.name}")
            except Exception as e:
                print(f"⚠️  RegimeDetector model load failed: {e}")
                self.model = None
        else:
            print("⚠️  RegimeDetector: No .pkl model found at", pkl_path)
            
    def _compute_features(self, df: pd.DataFrame) -> Optional[np.ndarray]:
        if len(df) < 50:
            return None
            
        df['return_1p'] = df['close'].pct_change(1)
        df['return_5p'] = df['close'].pct_change(5)
        
        df['sma_10'] = df['close'].rolling(10).mean()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr_14'] = df['tr'].rolling(14).mean()
        
        df['mom_10'] = (df['close'] - df['sma_10']) / df['sma_10']
        df['mom_50'] = (df['close'] - df['sma_50']) / df['sma_50']
        
        feature_cols = ['return_1p', 'return_5p', 'atr_14', 'mom_10', 'mom_50']
        # Use the latest row for prediction
        latest_features = df[feature_cols].iloc[-1].values
        
        if np.isnan(latest_features).any():
            return None
            
        return latest_features.reshape(1, -1)
        
    def update(self, price_data: Dict) -> MarketRegime:
        """Update regime based on new price data (Fallback if no model)"""
        if not price_data:
            return MarketRegime.UNKNOWN
            
        self.price_history.append(price_data)
        if len(self.price_history) > 60:
            self.price_history = self.price_history[-60:]
            
        if not self.model:
            # Fallback simple logic
            self.current_regime = MarketRegime.SIDEWAYS
            self.regime_confidence = 0.5
            return self.current_regime
            
        return self.detect_regime(self.price_history)
    
    def get_regime(self) -> MarketRegime:
        return self.current_regime
    
    def get_confidence(self) -> float:
        return self.regime_confidence
    
    def detect_regime(self, candles: List[Dict]) -> MarketRegime:
        """ML Prediction from candles"""
        if not candles or not self.model:
            return MarketRegime.UNKNOWN
            
        try:
            # Reformat to flat dicts
            parsed = []
            for c in candles:
                if 'mid' in c:
                    parsed.append({
                        'open': float(c['mid']['o']),
                        'high': float(c['mid']['h']),
                        'low': float(c['mid']['l']),
                        'close': float(c['mid']['c']),
                    })
                elif 'close' in c:
                    parsed.append({
                        'open': float(c.get('open', c['close'])),
                        'high': float(c.get('high', c['close'])),
                        'low': float(c.get('low', c['close'])),
                        'close': float(c['close']),
                    })
                    
            df = pd.DataFrame(parsed)
            features = self._compute_features(df)
            
            if features is not None:
                prediction = self.model.predict(features)[0]
                probabilities = self.model.predict_proba(features)[0]
                confidence = max(probabilities)
                
                # 0 = Sideways, 1 = Bull, 2 = Bear
                if prediction == 0:
                    self.current_regime = MarketRegime.SIDEWAYS
                elif prediction == 1:
                    self.current_regime = MarketRegime.BULL_MOD
                elif prediction == 2:
                    self.current_regime = MarketRegime.BEAR_MOD
                    
                self.regime_confidence = float(confidence)
                return self.current_regime
                
        except Exception as e:
            print(f"⚠️  ML Regime prediction error: {e}")
            
        self.current_regime = MarketRegime.UNKNOWN
        self.regime_confidence = 0.0
        return self.current_regime
