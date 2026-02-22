"use client";

import React, { useState, useEffect } from "react";
import { Plus, Trash2, Activity, ShieldAlert, BarChart3, TrendingDown, Percent, LayoutGrid, Info } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Tooltip,
    ResponsiveContainer,
    ScatterChart,
    Scatter,
    ZAxis,
    Cell,
    CartesianGrid,
    Label
} from "recharts";

interface Asset {
    ticker: string;
    weight: number;
}

interface Portfolio {
    id: string;
    name: string;
    assets: Asset[];
    rawInput: string;
    isBenchmark: boolean;
    results?: any;
}

const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
        return (
            <div className="glass-card" style={{ padding: '0.75rem', border: '1px solid var(--glass-border)', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.3)' }}>
                <p style={{ fontWeight: 600, color: 'white', marginBottom: '0.25rem' }}>{payload[0].payload.name}</p>
                {payload.map((entry: any, index: number) => (
                    <p key={index} style={{ fontSize: '0.875rem', color: entry.color }}>
                        {entry.name}: {entry.value.toFixed(2)}%
                    </p>
                ))}
            </div>
        );
    }
    return null;
};

export default function Home() {
    const [portfolios, setPortfolios] = useState<Portfolio[]>([
        {
            id: "1",
            name: "Main Portfolio",
            assets: [{ ticker: "SPY", weight: 50 }, { ticker: "QQQ", weight: 50 }],
            rawInput: "SPY 50\nQQQ 50",
            isBenchmark: false
        }
    ]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const parseInput = (text: string): Asset[] => {
        return text.split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0)
            .map(line => {
                const parts = line.split(/\s+/);
                const ticker = parts[0]?.toUpperCase() || "";
                const weight = parseFloat(parts[1]) || 0;
                return { ticker, weight };
            })
            .filter(asset => asset.ticker !== "");
    };

    const addPortfolio = () => {
        const id = Math.random().toString(36).substr(2, 9);
        setPortfolios([...portfolios, {
            id,
            name: `Comparison ${portfolios.length}`,
            assets: [],
            rawInput: "",
            isBenchmark: false
        }]);
    };

    const removePortfolio = (id: string) => {
        if (portfolios.length > 1) {
            setPortfolios(portfolios.filter(p => p.id !== id));
        }
    };

    const updatePortfolioInput = (portfolioId: string, text: string) => {
        setPortfolios(portfolios.map(p => {
            if (p.id === portfolioId) {
                return {
                    ...p,
                    rawInput: text,
                    assets: parseInput(text)
                };
            }
            return p;
        }));
    };

    const analyze = async () => {
        setLoading(true);
        setError(null);
        try {
            const updatedPortfolios = await Promise.all(portfolios.map(async (p) => {
                if (p.assets.length === 0) return p;

                const res = await fetch("/api/analyze", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        tickers: p.assets.map(a => a.ticker),
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

    const formatChartData = (p: Portfolio) => {
        if (!p.results || !p.results.risk_contribution) return [];
        return p.assets.map(asset => ({
            name: asset.ticker,
            risk: (p.results.risk_contribution[asset.ticker] || 0) * 100,
            size: asset.weight
        })).sort((a, b) => b.risk - a.risk);
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

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '2rem', marginBottom: '3rem' }}>
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

                        <div className="input-group" style={{ flexDirection: 'column', alignItems: 'stretch', marginBottom: '1.5rem' }}>
                            <label style={{ color: 'var(--muted)', fontSize: '0.875rem', marginBottom: '0.5rem', display: 'block' }}>
                                Enter "Ticker Allocation" per line (e.g. AAPL 50)
                            </label>
                            <textarea
                                placeholder="AAPL 50\nMSFT 50"
                                className="input-field"
                                style={{
                                    width: '100%',
                                    minHeight: '100px',
                                    fontFamily: 'monospace',
                                    resize: 'vertical',
                                    lineHeight: '1.5',
                                    padding: '1rem'
                                }}
                                value={p.rawInput}
                                onChange={(e) => updatePortfolioInput(p.id, e.target.value)}
                            />
                        </div>

                        {p.results && (
                            <div style={{ marginTop: '1rem', paddingTop: '1.5rem', borderTop: '1px solid var(--glass-border)' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '2rem' }}>
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
                                </div>

                                <div style={{ marginBottom: '2rem' }}>
                                    <h3 style={{ fontSize: '1rem', color: 'white', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <BarChart3 size={18} color="var(--primary)" /> Risk Contribution Breakdown (%)
                                    </h3>
                                    <div style={{ height: '200px', width: '100%' }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <BarChart data={formatChartData(p)} layout="vertical" margin={{ left: -20, right: 20 }}>
                                                <XAxis type="number" hide domain={[0, 100]} />
                                                <YAxis dataKey="name" type="category" stroke="var(--muted)" fontSize={12} tickLine={false} axisLine={false} width={60} />
                                                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.05)' }} />
                                                <Bar dataKey="risk" radius={[0, 4, 4, 0]} barSize={20}>
                                                    {formatChartData(p).map((entry, index) => (
                                                        <Cell key={`cell-${index}`} fill={index === 0 ? 'var(--accent)' : 'var(--primary)'} fillOpacity={0.8} />
                                                    ))}
                                                </Bar>
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>

                                <div>
                                    <h3 style={{ fontSize: '1rem', color: 'white', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <Percent size={18} color="var(--accent)" /> Risk vs. Position Size
                                    </h3>
                                    <div style={{ height: '200px', width: '100%' }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: -20 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                                                <XAxis type="number" dataKey="size" name="Position Size" unit="%" stroke="var(--muted)" fontSize={10}>
                                                    <Label value="Position Size (%)" position="bottom" offset={0} fill="var(--muted)" fontSize={10} />
                                                </XAxis>
                                                <YAxis type="number" dataKey="risk" name="Risk Contrib." unit="%" stroke="var(--muted)" fontSize={10}>
                                                    <Label value="Risk (%)" angle={-90} position="insideLeft" style={{ textAnchor: 'middle' }} fill="var(--muted)" fontSize={10} />
                                                </YAxis>
                                                <Tooltip content={<CustomTooltip />} />
                                                <Scatter name="Assets" data={formatChartData(p)} fill="var(--primary)">
                                                    {formatChartData(p).map((entry, index) => (
                                                        <Cell key={`cell-${index}`} fill={entry.risk > entry.size ? 'var(--accent)' : 'var(--primary)'} />
                                                    ))}
                                                </Scatter>
                                            </ScatterChart>
                                        </ResponsiveContainer>
                                    </div>
                                    <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.5rem', textAlign: 'center' }}>
                                        <Info size={12} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
                                        Assets in <span style={{ color: 'var(--accent)' }}>orange</span> are contributing disproportionate risk relative to their size.
                                    </p>
                                </div>
                            </div>
                        )}
                    </motion.div>
                ))}

                <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={addPortfolio}
                    style={{ border: '2px dashed var(--glass-border)', background: 'transparent', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem', color: 'var(--muted)', cursor: 'pointer', minHeight: '400px' }}
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
