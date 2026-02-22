# %%
import numpy as np
from scipy.optimize import fsolve

# %%
def solve_implied_growth(target_pe, n_years, r=0.11, g_terminal=0.03):
    """
    Solves for the implied growth rate (g) that justifies a specific P/E ratio.
    
    Formula logic:
    P/E = Sum of discounted earnings (Stage 1) + Terminal Value (Stage 2)
    """
    
    def pe_equation(g):
        # Stage 1: Present Value of Earnings for n years
        # P/E_stage1 = sum_{t=1}^{n} [ (1+g)^t / (1+r)^t ]
        # This is a geometric series: (1+g)/(r-g) * [1 - ((1+g)/(1+r))^n]
        stage1 = ((1 + g) / (r - g)) * (1 - ((1 + g) / (1 + r))**n_years)
        
        # Stage 2: Terminal Value discounted back to today
        # TV = [ E_n * (1 + g_terminal) ] / (r - g_terminal)
        # PV of TV = TV / (1 + r)^n
        terminal_value_at_n = ((1 + g)**n_years * (1 + g_terminal)) / (r - g_terminal)
        stage2 = terminal_value_at_n / (1 + r)**n_years
        
        return (stage1 + stage2) - target_pe

    # Initial guess for growth rate (e.g., 10%)
    initial_guess = 0.10
    
    # Use fsolve to find the root of the equation
    implied_g = fsolve(pe_equation, initial_guess)[0]
    
    return implied_g

#%%
# --- USER INPUTS ---
      # Plug in your P/E ratio here
years_of_growth = 10 # Plug in the high-growth time frame
market_return = 0.11 # Your 11% assumption
terminal_g = 0.03    # Your 3% assumption

for i in range(0,110,5):
    current_pe = i
    # Calculate
    result = solve_implied_growth(current_pe, years_of_growth, market_return, terminal_g)

    print(f"P/E of {current_pe}")
    print(f"Implies growth of: {result:.2%}/year.")
# %%
