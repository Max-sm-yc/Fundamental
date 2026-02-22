"use client";

import React, { useState, useEffect } from "react";
import { Plus, Trash2, Activity, ShieldAlert, BarChart3, TrendingDown, Percent } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface Asset {
    ticker: string;
    weight: number;
}

interface Portfolio {
    id: string;
    name: string;
    assets: Asset[];
    isBenchmark: boolean;
    results?: any;
}

export default function Home() {
    const [portfolios, setPortfolios] = useState<Portfolio[]>([
        { id: "1", name: "Main Portfolio", assets: [{ ticker: "SPY", weight: 0.5 }, { ticker: "QQQ", weight: 0.5 }], isBenchmark: false }
    ]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const addPortfolio = () => {
        const id = Math.random().toString(36).substr(2, 9);
        setPortfolios([...portfolios, { id, name: `Comparison ${portfolios.length}`, assets: [{ ticker: "", weight: 0 }], isBenchmark: false }]);
    };

    const removePortfolio = (id: string) => {
        if (portfolios.length > 1) {
            setPortfolios(portfolios.filter(p => p.id !== id));
        }
    };

    const addAsset = (portfolioId: string) => {
        setPortfolios(portfolios.map(p => {
            if (p.id === portfolioId) {
                return { ...p, assets: [...p.assets, { ticker: "", weight: 0 }] };
            }
            return p;
        }));
    };

    const updateAsset = (portfolioId: string, index: number, field: keyof Asset, value: string | number) => {
        setPortfolios(portfolios.map(p => {
            if (p.id === portfolioId) {
                const newAssets = [...p.assets];
                newAssets[index] = { ...newAssets[index], [field]: field === 'weight' ? parseFloat(value as string) || 0 : value };
                return { ...p, assets: newAssets };
            }
            return p;
        }));
    };

    const removeAsset = (portfolioId: string, index: number) => {
        setPortfolios(portfolios.map(p => {
            if (p.id === portfolioId && p.assets.length > 1) {
                const newAssets = p.assets.filter((_, i) => i !== index);
                return { ...p, assets: newAssets };
            }
            return p;
        }));
    };

    const analyze = async () => {
        setLoading(true);
        setError(null);
        try {
            const updatedPortfolios = await Promise.all(portfolios.map(async (p) => {
                const res = await fetch("/api/analyze", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        tickers: p.assets.map(a => a.ticker.toUpperCase()),
                        weights: p.assets.map(a => a.weight / 100), // convert to decimal
                    }),
                });
                if (!res.ok) throw new Error(await res.text());
                const data = await res.json();
                return { ...p, results: data };
            }));
            setPortfolios(updatedPortfolios);
        } catch (err: any) {
            setError(err.message || "An error occurred during analysis.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="premium-container">
            <header style={{ marginBottom: '3rem', textAlign: 'center' }}>
                <motion.h1
                    className="gradient-text"
                    style={{ fontSize: '3.5rem', fontWeight: 800, marginBottom: '1rem' }}
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    Aura Risk Engine
                </motion.h1>
                <p style={{ color: 'var(--muted)', fontSize: '1.2rem' }}>Tail-Aware Portfolio Risk Analytics & Comparative Analysis</p>
            </header>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '2rem', marginBottom: '3rem' }}>
                {portfolios.map((p) => (
                    <motion.div
                        key={p.id}
                        className="glass-card"
                        layout
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <input
                                value={p.name}
                                onChange={(e) => setPortfolios(portfolios.map(item => item.id === p.id ? { ...item, name: e.target.value } : item))}
                                style={{ background: 'transparent', border: 'none', color: 'white', fontSize: '1.25rem', fontWeight: 600, width: '100%' }}
                            />
                            <button onClick={() => removePortfolio(p.id)} style={{ color: 'var(--muted)', background: 'transparent', border: 'none', cursor: 'pointer' }}>
                                <Trash2 size={20} />
                            </button>
                        </div>

                        {p.assets.map((asset, idx) => (
                            <div key={idx} className="input-group">
                                <input
                                    placeholder="Ticker (e.g. NVDA)"
                                    className="input-field"
                                    value={asset.ticker}
                                    onChange={(e) => updateAsset(p.id, idx, 'ticker', e.target.value)}
                                />
                                <div style={{ position: 'relative', width: '100px' }}>
                                    <input
                                        type="number"
                                        placeholder="%"
                                        className="input-field"
                                        style={{ width: '100%' }}
                                        value={asset.weight || ""}
                                        onChange={(e) => updateAsset(p.id, idx, 'weight', e.target.value)}
                                    />
                                </div>
                                <button onClick={() => removeAsset(p.id, idx)} style={{ color: '#ef4444', background: 'transparent', border: 'none', padding: '0 0.5rem' }}>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        ))}

                        <button onClick={() => addAsset(p.id)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary)', background: 'transparent', border: 'none', marginTop: '1rem', cursor: 'pointer', fontWeight: 500 }}>
                            <Plus size={18} /> Add Asset
                        </button>

                        {p.results && (
                            <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--glass-border)' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div className="metric-card">
                                        <div className="metric-label">Volatility</div>
                                        <div className="metric-value" style={{ color: 'var(--primary)' }}>{(p.results.volatility * 100).toFixed(2)}%</div>
                                    </div>
                                    <div className="metric-card">
                                        <div className="metric-label">VaR (95%)</div>
                                        <div className="metric-value" style={{ color: 'var(--accent)' }}>{(p.results.var * 100).toFixed(2)}%</div>
                                    </div>
                                    <div className="metric-card">
                                        <div className="metric-label">Hist. CVaR</div>
                                        <div className="metric-value" style={{ color: '#ef4444' }}>{(p.results.cvar * 100).toFixed(2)}%</div>
                                    </div>
                                    <div className="metric-card">
                                        <div className="metric-label">Max Contrib.</div>
                                        <div className="metric-value" style={{ fontSize: '1.2rem', marginTop: '0.5rem' }}>
                                            {Object.entries(p.results.risk_contribution as Record<string, number>)
                                                .sort(([, a], [, b]) => b - a)[0][0]}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </motion.div>
                ))}

                <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={addPortfolio}
                    style={{ border: '2px dashed var(--glass-border)', background: 'transparent', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem', color: 'var(--muted)', cursor: 'pointer', minHeight: '300px' }}
                >
                    <Plus size={48} />
                    <span>Compare another portfolio</span>
                </motion.button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem' }}>
                <button
                    className="btn-primary"
                    onClick={analyze}
                    disabled={loading}
                    style={{ padding: '1rem 3rem', fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}
                >
                    {loading ? <Activity className="animate-spin" /> : <ShieldAlert />}
                    {loading ? "Calculating..." : "Run Analysis"}
                </button>
            </div>

            {
                error && (
                    <div style={{ marginTop: '2rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', borderRadius: '8px', color: '#ef4444', textAlign: 'center' }}>
                        {error}
                    </div>
                )
            }

            <footer style={{ marginTop: '5rem', textAlign: 'center', color: 'var(--muted)', fontSize: '0.875rem' }}>
                &copy; 2026 Aura Risk Engine. Data powered by yfinance. Parametric VaR & Historical CVaR methodologies.
            </footer>

            <style jsx global>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .animate-spin {
          animation: spin 1s linear infinite;
        }
      `}</style>
        </main >
    );
}
