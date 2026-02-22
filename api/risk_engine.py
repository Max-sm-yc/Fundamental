import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import norm
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class RiskEngine:
    def __init__(self, portfolio_weights: Dict[str, float], lookback_years: int = 5, confidence_level: float = 0.95, stress_weight: float = 0.4):
        self.weights = portfolio_weights
        self.tickers = list(portfolio_weights.keys())
        self.allocations = np.array(list(portfolio_weights.values()))
        self.lookback = lookback_years
        self.conf = confidence_level
        self.stress_weight = stress_weight
        self.proxy_ticker = 'SPY'
        
        # Validation and normalization
        total_weight = sum(self.allocations)
        if not np.isclose(total_weight, 1.0) and total_weight > 0:
            self.allocations = self.allocations / total_weight

    def fetch_and_backfill_data(self):
        start_date = (datetime.now() - timedelta(days=self.lookback * 365)).strftime('%Y-%m-%d')
        all_tickers = list(set(self.tickers + [self.proxy_ticker]))
        
        # Download data
        try:
            data = yf.download(all_tickers, start=start_date, progress=False)['Close']
        except Exception as e:
            raise Exception(f"Failed to fetch market data: {str(e)}")

        if isinstance(data, pd.Series):
            data = data.to_frame()

        # Calculate daily log returns
        returns = np.log(data / data.shift(1)).dropna(how='all')
        
        if self.proxy_ticker not in returns.columns:
            # Fallback if proxy download failed for some reason
            proxy_returns = pd.Series(0, index=returns.index)
        else:
            proxy_returns = returns[self.proxy_ticker].fillna(0)
            
        port_returns_df = returns[self.tickers].copy() if all(t in returns.columns for t in self.tickers) else returns.reindex(columns=self.tickers).fillna(0)
        
        for ticker in self.tickers:
            if ticker not in returns.columns or returns[ticker].isnull().all():
                port_returns_df[ticker] = proxy_returns # Simple fallback
                continue

            first_valid = port_returns_df[ticker].first_valid_index()
            if first_valid is not None and first_valid > port_returns_df.index[5]:
                valid_data = port_returns_df[ticker].dropna()
                common_index = valid_data.index.intersection(proxy_returns.index)
                
                if len(common_index) > 10:
                    y = valid_data.loc[common_index]
                    x = proxy_returns.loc[common_index]
                    covariance = np.cov(x, y)[0, 1]
                    variance = np.var(x)
                    beta = covariance / variance if variance != 0 else 1.0
                    missing_index = proxy_returns.index.difference(valid_data.index)
                    synthetic_returns = proxy_returns.loc[missing_index] * beta
                    port_returns_df.loc[missing_index, ticker] = synthetic_returns

        port_returns_df.fillna(0, inplace=True)
        self.returns_df = port_returns_df
        return port_returns_df

    def calculate_tail_aware_covariance(self):
        normal_cov = self.returns_df.cov()
        daily_port_returns = self.returns_df.dot(self.allocations)
        
        cutoff = daily_port_returns.quantile(0.05)
        stress_days = self.returns_df[daily_port_returns <= cutoff]
        
        if len(stress_days) < 2:
            return normal_cov

        tail_cov = stress_days.cov()
        tail_cov.fillna(normal_cov, inplace=True) 
        blended_cov = (1 - self.stress_weight) * normal_cov + (self.stress_weight) * tail_cov
        return blended_cov

    def generate_metrics(self):
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        blended_cov = self.calculate_tail_aware_covariance()
        port_variance = np.dot(self.allocations.T, np.dot(blended_cov, self.allocations))
        port_std = np.sqrt(port_variance)
        z_score = norm.ppf(1 - self.conf)
        var_parametric_pct = - (z_score * port_std)
        
        historical_returns = self.returns_df.dot(self.allocations)
        sorted_returns = historical_returns.sort_values(ascending=True)
        cutoff_index = int((1 - self.conf) * len(sorted_returns))
        
        if cutoff_index > 0:
            tail_losses = sorted_returns.iloc[:cutoff_index]
            cvar_historical_pct = - tail_losses.mean()
        else:
            cvar_historical_pct = 0.0
            
        mvar_vector = np.dot(blended_cov, self.allocations) / port_std if port_std != 0 else np.zeros(len(self.allocations))
        risk_contrib_pct = mvar_vector * self.allocations
        total_risk_contrib = sum(risk_contrib_pct)
        risk_contrib_ratio = risk_contrib_pct / total_risk_contrib if total_risk_contrib != 0 else self.allocations

        return {
            "volatility": float(port_std),
            "var": float(var_parametric_pct),
            "cvar": float(cvar_historical_pct),
            "risk_contribution": dict(zip(self.tickers, [float(v) for v in risk_contrib_ratio]))
        }
