import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import norm
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

class RiskEngine:
    def __init__(self, pm_configs: Dict[str, Dict[str, float]], lookback_years: int = 5, confidence_level: float = 0.95, stress_weight: float = 0.4, expected_returns: Optional[Dict[str, float]] = None):
        self.pm_configs = pm_configs
        self.lookback = lookback_years
        self.conf = confidence_level
        self.stress_weight = stress_weight
        self.expected_returns = expected_returns
        self.proxy_ticker = 'SPY'
        
        # Flatten PM -> Asset weights for core calculation
        self.asset_weights = {}
        for pm_name, assets in pm_configs.items():
            for ticker, weight in assets.items():
                self.asset_weights[ticker] = self.asset_weights.get(ticker, 0) + weight
        
        self.tickers = list(self.asset_weights.keys())
        self.allocations = np.array(list(self.asset_weights.values()))
        
        # Validation and normalization
        total_weight = sum(self.allocations)
        if not np.isclose(total_weight, 1.0) and total_weight > 0:
            self.allocations = self.allocations / total_weight
            # Re-sync asset_weights dictionary
            self.asset_weights = dict(zip(self.tickers, self.allocations))

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
        """Calculates Component CVaR for each PM (Aggregated from underlying assets)."""
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        port_returns = self.returns_df.dot(self.allocations)
        var_threshold = port_returns.quantile(1 - self.conf)
        
        # Identify Tail Scenarios
        tail_scenarios = self.returns_df[port_returns <= var_threshold]
        
        if tail_scenarios.empty:
            return {pm: 0.0 for pm in self.pm_configs.keys()}
            
        # Marginal CVaR per Asset
        marginal_cvar_assets = -tail_scenarios.mean()
        
        # Aggregate to PM level
        pm_cvars_abs = {}
        for pm_name, assets in self.pm_configs.items():
            pm_contribution = 0
            for ticker, weight in assets.items():
                pm_contribution += marginal_cvar_assets.get(ticker, 0) * weight
            pm_cvars_abs[pm_name] = pm_contribution
            
        total_pm_risk = sum(pm_cvars_abs.values())
        
        # Normalize to proportion (summing to 100%)
        if total_pm_risk != 0:
            return {pm: val / total_pm_risk for pm, val in pm_cvars_abs.items()}
        return {pm: 0.0 for pm in self.pm_configs.keys()}

    def calculate_raroc(self, risk_free_rate: float = 0.02) -> Dict[str, float]:
        """Calculates RAROC at the PM level based on their basket performance."""
        pm_cvars = self.calculate_component_cvar()
        
        # Calculate PM-level expected returns (weighted average of assets)
        if self.expected_returns is None:
            asset_exp_rets = self.returns_df.mean() * 252
        else:
            asset_exp_rets = pd.Series(self.expected_returns)

        raroc = {}
        for pm_name, assets in self.pm_configs.items():
            # PM Expected Return = sum( Asset Weight * Asset Exp Return ) / sum( Asset Weights )
            pm_total_weight = sum(assets.values())
            if pm_total_weight == 0:
                raroc[pm_name] = 0.0
                continue
                
            pm_exp_ret = sum(weight * asset_exp_rets.get(ticker, 0) for ticker, weight in assets.items()) / pm_total_weight
            risk = pm_cvars.get(pm_name, 0)
            reward = pm_exp_ret - risk_free_rate
            
            if risk > 0:
                raroc[pm_name] = reward / risk
            elif risk < 0:
                raroc[pm_name] = float('inf')
            else:
                raroc[pm_name] = 0.0
                
        return raroc

    def calculate_cluster_penalty(self) -> Dict[str, float]:
        """Identifies clusters of PMs by comparing their aggregate basket returns."""
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        # Create PM-level daily returns
        pm_returns = {}
        for pm_name, assets in self.pm_configs.items():
            pm_total_weight = sum(assets.values())
            if pm_total_weight > 0:
                pm_returns[pm_name] = sum(self.returns_df[ticker] * (weight / pm_total_weight) for ticker, weight in assets.items())
            else:
                pm_returns[pm_name] = pd.Series(0, index=self.returns_df.index)
        
        pm_returns_df = pd.DataFrame(pm_returns)
        corr = pm_returns_df.corr().fillna(0)
        dist = np.sqrt(2 * (1 - corr))
        
        try:
            linkage_matrix = linkage(squareform(dist), method='ward')
            clusters = fcluster(linkage_matrix, 0.5, criterion='distance')
            cluster_map = dict(zip(pm_returns_df.columns, clusters))
            cluster_counts = pd.Series(clusters).value_counts()
            
            return {pm: 1.0 / cluster_counts[cluster_map[pm]] for pm in self.pm_configs.keys()}
        except Exception:
            return {pm: 1.0 for pm in self.pm_configs.keys()}

    def apply_hard_limits(self, cvar_limit_pct: float = 0.05) -> Dict[str, float]:
        """Scales PM allocations down if their Aggregate Component CVaR exceeds the hard limit."""
        pm_cvars = self.calculate_component_cvar()
        pm_weights = {pm: sum(assets.values()) for pm, assets in self.pm_configs.items()}
        
        final_pm_weights = {}
        for pm, weight in pm_weights.items():
            contribution = pm_cvars.get(pm, 0)
            if contribution > cvar_limit_pct:
                scalar = cvar_limit_pct / contribution
                final_pm_weights[pm] = weight * scalar
            else:
                final_pm_weights[pm] = weight
                
        return final_pm_weights

    def optimize_allocation(self, target_leverage: float = 1.0) -> Dict[str, float]:
        """Synthesizes metrics to suggest optimal capital allocation across PMs."""
        raroc = self.calculate_raroc()
        penalties = self.calculate_cluster_penalty()
        
        pm_names = list(self.pm_configs.keys())
        scores = np.array([raroc.get(pm, 0) * penalties.get(pm, 1.0) for pm in pm_names])
        scores = np.clip(scores, 0, 100)
        
        if scores.sum() == 0:
            target_weights = {pm: 1.0/len(pm_names) for pm in pm_names}
        else:
            target_weights = dict(zip(pm_names, (scores / scores.sum() * target_leverage).tolist()))
            
        # For hard limits, we need to temporarily re-run CVaR with these weights
        # But for 'minimal' change, we'll apply them to the current PM weights
        final_weights = {}
        pm_cvars = self.calculate_component_cvar()
        for pm, t_weight in target_weights.items():
            contrib = pm_cvars.get(pm, 0) * (t_weight / max(0.0001, sum(self.pm_configs[pm].values())))
            if contrib > 0.05: # Hard limit 5%
                final_weights[pm] = t_weight * (0.05 / contrib)
            else:
                final_weights[pm] = t_weight
        
        return final_weights

    def generate_metrics(self):
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        # Standard metrics for backward compatibility
        blended_cov = self.calculate_tail_aware_covariance()
        port_variance = np.dot(self.allocations.T, np.dot(blended_cov, self.allocations))
        port_std = np.sqrt(port_variance)
        
        z_score = norm.ppf(1 - self.conf)
        var_parametric_pct = -(z_score * port_std)
        
        historical_returns = self.returns_df.dot(self.allocations)
        cvar_historical_pct = -historical_returns[historical_returns <= historical_returns.quantile(1-self.conf)].mean()
        
        # Hierarchical PM Metrics
        pm_cvars = self.calculate_component_cvar()
        pm_raroc = self.calculate_raroc()
        pm_optimized = self.optimize_allocation()

        # Identify individual asset contributions for deep dive
        # (This satisfies the 'risk_contribution' requirement of the current chart)
        port_returns = self.returns_df.dot(self.allocations)
        tail_scenarios = self.returns_df[port_returns <= port_returns.quantile(1 - self.conf)]
        asset_marginal_cvar = -tail_scenarios.mean() if not tail_scenarios.empty else pd.Series(0, index=self.tickers)
        
        # Absolute contributions
        abs_contributions = asset_marginal_cvar * pd.Series(self.asset_weights)
        total_abs_risk = abs_contributions.sum()
        
        # Normalize to proportion (summing to 100%)
        asset_contributions = (abs_contributions / total_abs_risk).fillna(0).to_dict() if total_abs_risk != 0 else {t: 0.0 for t in self.tickers}

        return {
            "volatility": float(port_std),
            "var": float(var_parametric_pct),
            "cvar": float(cvar_historical_pct),
            "risk_contribution": asset_contributions, # Asset level for detailed chart
            "portfolio_volatility": float(port_std),
            "portfolio_cvar": float(cvar_historical_pct),
            "component_cvar": pm_cvars, # PM level
            "raroc": pm_raroc,
            "target_allocation": pm_optimized,
            "current_allocation": {pm: sum(assets.values()) for pm, assets in self.pm_configs.items()}
        }
