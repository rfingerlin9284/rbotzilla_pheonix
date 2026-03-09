#!/usr/bin/env python3
"""
train_initial_ml_model.py
Bootstraps the ML Infrastructure (Phase 3 Integration)

This script:
1. Connects to OANDA using practice credentials
2. Pulls 1,000 recent candles for major pairs
3. Calculates momentum/volatility features
4. Trains a RandomForestClassifier to detect Market Regimes (Bull/Bear/Sideways)
5. Saves the trained model to ml_learning/models/random_forest.pkl
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import pickle
from datetime import datetime
from dotenv import load_dotenv

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
except ImportError:
    print("❌ ERROR: scikit-learn is not installed. Please run: pip install scikit-learn pandas numpy")
    sys.exit(1)

# Add parent dir to path to import brokers
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from brokers.oanda_connector import OandaConnector

def compute_features(df):
    """Calculate technical features for ML training"""
    if len(df) < 50:
        return df

    # Returns
    df['return_1p'] = df['close'].pct_change(1)
    df['return_5p'] = df['close'].pct_change(5)
    
    # Moving Averages
    df['sma_10'] = df['close'].rolling(10).mean()
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    
    # Volatility / ATR proxy
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr_14'] = df['tr'].rolling(14).mean()
    
    # Momentum indicators
    df['mom_10'] = (df['close'] - df['sma_10']) / df['sma_10']
    df['mom_50'] = (df['close'] - df['sma_50']) / df['sma_50']
    
    return df.dropna()

def extract_labels(df):
    """
    Define what regime the market was actually in, looking forward 5 periods:
    0 = Sideways (range < 0.1%)
    1 = Bull (return > 0.1%)
    2 = Bear (return < -0.1%)
    """
    future_return = df['close'].shift(-5) / df['close'] - 1.0
    
    conditions = [
        (future_return > 0.001),
        (future_return < -0.001)
    ]
    choices = [1, 2] # Bull, Bear
    # Default to 0 (Sideways)
    df['target_regime'] = np.select(conditions, choices, default=0)
    
    # Drop the NaN rows at the very end
    return df.dropna(subset=['target_regime'])

def main():
    print("==================================================")
    print("🤖 INITIATING ML REGIME MODEL TRAINING SEQUENCE")
    print("==================================================")
    
    load_dotenv(project_root / '.env')
    
    print("1. Connecting to OANDA to gather training data...")
    oanda = OandaConnector(environment="practice")
    
    if not oanda._validate_connection():
        print("❌ Could not connect to OANDA. Cannot pull training data.")
        sys.exit(1)
        
    pairs = ['EUR_USD', 'GBP_USD', 'USD_JPY']
    all_features = []
    
    for pair in pairs:
        print(f"2. Pulling 1,000 recent D1 candles for {pair}...")
        try:
            # Get 1000 H1 candles to represent recent market behavior
            candles = oanda.get_historical_data(pair, count=1000, granularity="H1")
            if not candles:
                print(f"⚠️  No data returned for {pair}")
                continue
                
            parsed_data = []
            for c in candles:
                if 'mid' not in c: continue
                parsed_data.append({
                    'time': c.get('time'),
                    'volume': c.get('volume', 0),
                    'open': c['mid']['o'],
                    'high': c['mid']['h'],
                    'low': c['mid']['l'],
                    'close': c['mid']['c']
                })
                
            df = pd.DataFrame(parsed_data)
            # Ensure columns are float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            print(f"3. Computing technical features and momentum vectors for {pair}...")
            df = compute_features(df)
            df = extract_labels(df)
            
            all_features.append(df)
            
        except Exception as e:
            print(f"⚠️  Failed processing {pair}: {e}")
            
    if not all_features:
        print("❌ Failed to gather any training data.")
        sys.exit(1)
        
    # Combine datasets
    master_df = pd.concat(all_features, ignore_index=True)
    
    # Define feature columns
    feature_cols = ['return_1p', 'return_5p', 'atr_14', 'mom_10', 'mom_50']
    
    X = master_df[feature_cols].values
    y = master_df['target_regime'].values
    
    print(f"\n4. Assembled dataset with {len(X)} samples.")
    print("5. Training RandomForest Classifier across Regimes...")
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, class_weight='balanced')
    clf.fit(X_train, y_train)
    
    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"\n✅ Training Complete! Model Accuracy on test set: {accuracy:.2%}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['Sideways', 'Bull', 'Bear']))
    
    print("6. Serializing and saving neural payload to .pkl format...")
    models_dir = project_root / 'ml_learning' / 'models'
    models_dir.mkdir(parents=True, exist_ok=True)
    
    pkl_path = models_dir / 'random_forest.pkl'
    
    with open(pkl_path, 'wb') as f:
        pickle.dump(clf, f)
        
    print(f"\n🎉 SUCCESS: Initial ML Model compiled and stored at: {pkl_path}")
    print("The OANDA Trading Engine will now have predictive capabilities active on next boot.")
    print("==================================================")

if __name__ == "__main__":
    main()
