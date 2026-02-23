import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import norm
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

class RiskEngine:
    def __init__(self, portfolio_weights: Dict[str, float], lookback_years: int = 5, confidence_level: float = 0.95, stress_weight: float = 0.4, expected_returns: Optional[Dict[str, float]] = None):
        self.weights = portfolio_weights
        self.tickers = list(portfolio_weights.keys())
        self.allocations = np.array(list(portfolio_weights.values()))
        self.lookback = lookback_years
        self.conf = confidence_level
        self.stress_weight = stress_weight
        self.expected_returns = expected_returns
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

    def calculate_component_cvar(self) -> Dict[str, float]:
        """Calculates Component CVaR using Euler Decomposition (Historical Simulation)."""
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        port_returns = self.returns_df.dot(self.allocations)
        var_threshold = port_returns.quantile(1 - self.conf)
        
        # Identify Tail Scenarios (losses worse than VaR)
        tail_scenarios = self.returns_df[port_returns <= var_threshold]
        
        if tail_scenarios.empty:
            return {ticker: 0.0 for ticker in self.tickers}
            
        # Marginal CVaR: average return of each PM during tail events
        marginal_cvar = -tail_scenarios.mean()
        
        # Component CVaR = Marginal CVaR * Weight
        # (This decomposes the total Portfolio CVaR: sum(Component CVaR) = Portfolio CVaR)
        component_cvar = marginal_cvar * pd.Series(dict(zip(self.tickers, self.allocations)))
        
        return component_cvar.to_dict()

    def calculate_raroc(self, risk_free_rate: float = 0.02) -> Dict[str, float]:
        """Calculates Risk-Adjusted Return on Capital (RAROC) using Component CVaR."""
        comp_cvar = self.calculate_component_cvar()
        
        if self.expected_returns is None:
            # Fallback: calculate T12M average returns
            exp_rets = self.returns_df.mean() * 252
        else:
            exp_rets = pd.Series(self.expected_returns)

        raroc = {}
        rf_daily = risk_free_rate / 252 # Rough approximation if needed, but RAROC usually uses annual
        
        for ticker in self.tickers:
            risk = comp_cvar.get(ticker, 0)
            reward = exp_rets.get(ticker, 0) - risk_free_rate
            
            if risk > 0:
                raroc[ticker] = reward / risk
            elif risk < 0:
                # Negative risk means they hedge the tail - highly valuable
                raroc[ticker] = float('inf')
            else:
                raroc[ticker] = 0.0
                
        return raroc

    def calculate_cluster_penalty(self) -> Dict[str, float]:
        """Identifies clusters of correlated PMs and generates a penalty score."""
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        corr = self.returns_df.corr().fillna(0)
        # Distance Matrix D = sqrt(2 * (1 - rho))
        dist = np.sqrt(2 * (1 - corr))
        
        # Linkage
        try:
            linkage_matrix = linkage(squareform(dist), method='ward')
            # Extract clusters at a certain threshold (e.g., 0.5 distance)
            clusters = fcluster(linkage_matrix, 0.5, criterion='distance')
            cluster_map = dict(zip(self.tickers, clusters))
            
            # Penalty logic: 1 / size_of_cluster
            cluster_counts = pd.Series(clusters).value_counts()
            penalties = {ticker: 1.0 / cluster_counts[cluster_map[ticker]] for ticker in self.tickers}
            return penalties
        except Exception:
            return {ticker: 1.0 for ticker in self.tickers}

    def apply_hard_limits(self, cvar_limit_pct: float = 0.05) -> np.array:
        """Scales weights down if their Component CVaR exceeds the hard limit."""
        comp_cvar = self.calculate_component_cvar()
        capped_weights = self.allocations.copy()
        
        for i, ticker in enumerate(self.tickers):
            contribution = comp_cvar.get(ticker, 0)
            if contribution > cvar_limit_pct:
                scalar = cvar_limit_pct / contribution
                capped_weights[i] *= scalar
                
        return capped_weights

    def optimize_allocation(self, target_leverage: float = 1.0) -> Dict[str, float]:
        """Synthesizes RAROC, Cluster Penalties, and Hard Limits into a final target allocation."""
        raroc = self.calculate_raroc()
        penalties = self.calculate_cluster_penalty()
        
        # Score = RAROC * Penalty (rewarding efficiency and uniqueness)
        scores = np.array([raroc.get(t, 0) * penalties.get(t, 1.0) for t in self.tickers])
        
        # Handle inf/negative RAROC for weighting
        scores = np.clip(scores, 0, 100) # Simple clipping for stability
        
        if scores.sum() == 0:
            target_weights = self.allocations
        else:
            target_weights = scores / scores.sum() * target_leverage
            
        # Apply Hard Limits
        # Adjust target weights if they violate CVaR constraints
        # Temporary update self.allocations to target_weights to check limits
        original_allocations = self.allocations
        self.allocations = target_weights
        final_weights = self.apply_hard_limits()
        self.allocations = original_allocations # Restore
        
        # Re-normalize
        if final_weights.sum() > 0:
            final_weights = (final_weights / final_weights.sum()) * target_leverage
            
        return dict(zip(self.tickers, [float(w) for w in final_weights]))

    def generate_metrics(self):
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        # Standard metrics for backward compatibility
        blended_cov = self.calculate_tail_aware_covariance()
        port_variance = np.dot(self.allocations.T, np.dot(blended_cov, self.allocations))
        port_std = np.sqrt(port_variance)
        
        # Restore Parametric VaR
        z_score = norm.ppf(1 - self.conf)
        var_parametric_pct = -(z_score * port_std)
        
        historical_returns = self.returns_df.dot(self.allocations)
        cvar_historical_pct = -historical_returns[historical_returns <= historical_returns.quantile(1-self.conf)].mean()
        
        # New Framework Metrics
        comp_cvar = self.calculate_component_cvar()
        raroc = self.calculate_raroc()
        optimized = self.optimize_allocation()

        # Return a superset that satisfies AnalysisResponse and adds new features
        return {
            "volatility": float(port_std),
            "var": float(var_parametric_pct),
            "cvar": float(cvar_historical_pct),
            "risk_contribution": comp_cvar, # Alias Component CVaR for the chart
            "portfolio_volatility": float(port_std),
            "portfolio_cvar": float(cvar_historical_pct),
            "component_cvar": comp_cvar,
            "raroc": raroc,
            "target_allocation": optimized,
            "current_allocation": dict(zip(self.tickers, self.allocations.tolist()))
        }
