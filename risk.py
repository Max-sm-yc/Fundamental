import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import norm
from datetime import datetime, timedelta

class RiskEngine:
    def __init__(self, portfolio_weights, lookback_years=5, confidence_level=0.95, stress_weight=0.4):
        """
        :param portfolio_weights: Dictionary {Ticker: Weight}
        :param lookback_years: History length to fetch
        :param confidence_level: Confidence for VaR (e.g., 0.95)
        :param stress_weight: Weight given to the 'Tail Covariance' matrix (0 to 1)
        """
        self.weights = portfolio_weights
        self.tickers = list(portfolio_weights.keys())
        self.allocations = np.array(list(portfolio_weights.values()))
        self.lookback = lookback_years
        self.conf = confidence_level
        self.stress_weight = stress_weight
        self.proxy_ticker = 'SPY'  # Default proxy for backfilling
        
        # Validation
        if not np.isclose(sum(self.allocations), 1.0):
            print(f"Warning: Portfolio weights sum to {sum(self.allocations)}. Normalizing...")
            self.allocations = self.allocations / sum(self.allocations)

    def fetch_and_backfill_data(self):
        """
        Fetches data. If a stock is too young, it calculates Beta vs SPY
        during the overlapping period and backfills missing history using 
        that Beta * SPY_Returns.
        """
        print("Fetching market data...")
        start_date = (datetime.now() - timedelta(days=self.lookback * 365)).strftime('%Y-%m-%d')
        
        # We fetch the portfolio tickers PLUS the proxy
        all_tickers = self.tickers + [self.proxy_ticker]
        data = yf.download(all_tickers, start=start_date, progress=False)['Close']
        
        # Calculate daily log returns
        returns = np.log(data / data.shift(1)).dropna(how='all')
        
        # Separate Proxy and Portfolio Returns
        proxy_returns = returns[self.proxy_ticker].fillna(0)
        port_returns_df = returns[self.tickers].copy()
        
        # --- The Backfill Logic ---
        # Find the max length we expect
        full_length = len(proxy_returns)
        
        for ticker in self.tickers:
            # Check if this ticker has significant missing data at the start
            first_valid = port_returns_df[ticker].first_valid_index()
            
            # If the stock starts significantly later than our proxy
            if first_valid > port_returns_df.index[5]: # Allow a tiny buffer
                print(f"  > Backfilling history for {ticker} using Proxy ({self.proxy_ticker})...")
                
                # 1. Slice data to where both exist (the "Overlapping Period")
                valid_data = port_returns_df[ticker].dropna()
                common_index = valid_data.index.intersection(proxy_returns.index)
                
                y = valid_data.loc[common_index]
                x = proxy_returns.loc[common_index]
                
                # 2. Calculate Beta (Covariance / Variance)
                covariance = np.cov(x, y)[0, 1]
                variance = np.var(x)
                beta = covariance / variance
                
                # 3. Generate Synthetic History
                # We identify the missing dates
                missing_index = proxy_returns.index.difference(valid_data.index)
                
                # Synthetic Return = Proxy Return * Beta
                synthetic_returns = proxy_returns.loc[missing_index] * beta
                
                # 4. Fill the gaps
                port_returns_df.loc[missing_index, ticker] = synthetic_returns

        # Fill any remaining small gaps (like holidays specific to one exchange)
        port_returns_df.fillna(0, inplace=True)
        
        self.returns_df = port_returns_df
        return port_returns_df

    def calculate_tail_aware_covariance(self):
        """
        Calculates a blended covariance matrix.
        Matrix = (1 - w) * Normal_Cov + (w) * Tail_Cov
        Tail_Cov is derived from the worst 5% of market days.
        """
        # 1. Normal Covariance
        normal_cov = self.returns_df.cov()
        
        # 2. Identify Stress Days (Market Tail)
        # We create an equal-weight portfolio of the holdings to act as the "Market" reference
        # or we could use the Proxy. Let's use the actual portfolio returns for accuracy.
        daily_port_returns = self.returns_df.dot(self.allocations)
        
        cutoff = daily_port_returns.quantile(0.05) # Bottom 5% threshold
        stress_days = self.returns_df[daily_port_returns <= cutoff]
        
        # 3. Tail Covariance
        tail_cov = stress_days.cov()
        
        # Handle cases where tail_cov might have NaNs (rare, but good safety)
        tail_cov.fillna(normal_cov, inplace=True) 

        # 4. Blend them
        # This increases correlations and volatility based on stress_weight
        blended_cov = (1 - self.stress_weight) * normal_cov + (self.stress_weight) * tail_cov
        
        return blended_cov

    def generate_metrics(self):
        """
        Calculates VaR, CVaR using the logic defined.
        """
        if not hasattr(self, 'returns_df'):
            self.fetch_and_backfill_data()
            
        # --- 1. Parametric VaR (using Tail-Aware Covariance) ---
        blended_cov = self.calculate_tail_aware_covariance()
        
        # Portfolio Variance = w^T * Cov_Matrix * w
        port_variance = np.dot(self.allocations.T, np.dot(blended_cov, self.allocations))
        port_std = np.sqrt(port_variance)
        
        # Z-score for the confidence level
        z_score = norm.ppf(1 - self.conf) # Returns negative value, e.g., -1.645
        
        # Parametric VaR (Percentage)
        # We assume 0 mean return for conservative risk estimation (Standard Practice)
        var_parametric_pct = - (0 + z_score * port_std)
        
        # --- 2. Historical CVaR (Expected Shortfall) ---
        # We use the FULL history (including backfilled data)
        historical_returns = self.returns_df.dot(self.allocations)
        
        # Sort returns
        sorted_returns = historical_returns.sort_values(ascending=True)
        
        # Find the cutoff index
        cutoff_index = int((1 - self.conf) * len(sorted_returns))
        
        # CVaR is the average of losses exceeding the cutoff
        tail_losses = sorted_returns.iloc[:cutoff_index]
        cvar_historical_pct = - tail_losses.mean()
        
        # --- 3. Marginal Risk Contribution ---
        # Marginal VaR = (Cov * weights) / port_std
        mvar_vector = np.dot(blended_cov, self.allocations) / port_std
        risk_contrib_pct = mvar_vector * self.allocations
        risk_contrib_ratio = risk_contrib_pct / sum(risk_contrib_pct)

        return {
            "VaR_Parametric": var_parametric_pct,
            "CVaR_Historical": cvar_historical_pct,
            "Volatility_Daily": port_std,
            "Risk_Contribution": dict(zip(self.tickers, risk_contrib_ratio))
        }

# --- Execution ---

if __name__ == "__main__":
    # Define a portfolio
    my_portfolio = {
        'BIL': 0.187,
        'SMH': 0.302,
        'VDE': 0.052,
        'VFH':  0.111,
        'VIS': 0.104,
        'NLR': 0.033,
        'SKYY': 0.013,
        'IGF': 0.029,
        'ONLN': 0.007,
        'GE': 0.075,
        'GEV': 0.029,
        'GOOG': 0.055,
        'NFLX': 0.005
    }

    
#     Cash	SMH	VDE	VFH	VIS	NLR	SKYY	IGF	ONLN	GE	GEV	GOOG	NFLX
# 18.7%	30.2%	5.2%	11.1%	10.4%	3.3%	1.3%	2.9%	0.7%	7.5%	2.9%	5.5%	0.5%

    
    # Initialize Engine
    # stress_weight=0.5 means we treat "Panic Mode" correlations as 50% of the reality
    engine = RiskEngine(my_portfolio, lookback_years=5, confidence_level=0.95, stress_weight=0.5)
    
    # Run
    results = engine.generate_metrics()
    
    # Output Report
    print("\n" + "="*40)
    print(f"RISK REPORT (Confidence: {engine.conf*100}%)")
    print("="*40)
    print(f"Daily Volatility:      {results['Volatility_Daily']:.4%}")
    print(f"Parametric VaR:        {results['VaR_Parametric']:.4%}")
    print(f"Historical CVaR:       {results['CVaR_Historical']:.4%}")
    print("-" * 40)
    print("Risk Contribution by Asset:")
    for ticker, contrib in results['Risk_Contribution'].items():
        print(f"  {ticker}: {contrib:.2%}")
    print("="*40)