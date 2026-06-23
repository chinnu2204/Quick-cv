import React, { useState, useEffect } from 'react';
import { Terminal, Shield, Wallet, Cpu, CheckCircle, RefreshCw, Layers, Database } from 'lucide-react';

interface LogEntry {
  time: string;
  level: string;
  category: string;
  message: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'status' | 'logs'>('status');
  const [logs, setLogs] = useState<LogEntry[]>([
    { time: '00:16:32', level: 'INFO', category: 'INIT_DB', message: 'SQLite database setup check successful.' },
    { time: '00:16:33', level: 'INFO', category: 'SEED_SETTINGS', message: 'Seeded default models registry, deepseek-v4-flash-free active' },
    { time: '00:16:34', level: 'INFO', category: 'CORE_STARTUP', message: 'QuickCVBot initiated with polling mode...' },
    { time: '00:16:34', level: 'INFO', category: 'CORE_STARTUP', message: 'QuickCVPanelBot initiated with secure admin token...' },
    { time: '00:16:35', level: 'INFO', category: 'CORE_STARTUP', message: 'QuickCVCreditBot transactional alerts loop is active' }
  ]);

  const [botStatus, setBotStatus] = useState({
    userBot: 'ACTIVE',
    adminBot: 'ACTIVE',
    creditBot: 'ACTIVE',
    databaseConnection: 'OK',
    activeModel: 'DeepSeek V4 Flash'
  });

  const [stats, setStats] = useState({
    totalUsers: 24,
    resumesDrafted: 38,
    todayDrafts: 5,
    creditsRemaining: 48
  });

  // Simple auto simulation of logs to keep the diagnostic console feeling alive during preview
  useEffect(() => {
    const timer = setInterval(() => {
      const hours = String(new Date().getHours()).padStart(2, '0');
      const mins = String(new Date().getMinutes()).padStart(2, '0');
      const secs = String(new Date().getSeconds()).padStart(2, '0');
      const timeStr = `${hours}:${mins}:${secs}`;
      
      const simulatedCategories = [
        { cat: 'TELEMETRY_POLL', msg: 'System check ping verified healthy loops.' },
        { cat: 'DB_AUTO_COMPACT', msg: 'SQLite cache and indexing cleanups completed.' },
        { cat: 'CREDIT_AUDIT', msg: 'Verified credit limits for registered user accounts.' }
      ];
      const pick = simulatedCategories[Math.floor(Math.random() * simulatedCategories.length)];
      
      setLogs(prev => [
        { time: timeStr, level: 'INFO', category: pick.cat, message: pick.msg },
        ...prev.slice(0, 19) // limit to 20 logs in view
      ]);
    }, 15000);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen bg-[#0b0c10] text-[#c5c6c7] font-sans antialiased selection:bg-teal-500 selection:text-black">
      
      {/* Visual background gradient accents */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-teal-500/5 rounded-full filter blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-10 right-1/4 w-96 h-96 bg-indigo-500/5 rounded-full filter blur-[120px] pointer-events-none"></div>

      <div className="max-w-6xl mx-auto px-4 py-8 relative z-10">
        
        {/* Header Console Banner */}
        <header className="flex flex-col md:flex-row items-start md:items-center justify-between border-b border-gray-800 pb-6 mb-8 gap-4">
          <div>
            <div className="flex items-center gap-3">
              <span className="p-2 bg-teal-500/10 text-teal-400 rounded-lg border border-teal-500/20">
                <Cpu size={24} />
              </span>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2 font-mono">
                  QuickCV <span className="text-xs bg-slate-800 text-slate-300 font-normal px-2 py-0.5 rounded-full font-sans border border-slate-700">CORE SERVER</span>
                </h1>
                <p className="text-xs text-slate-500 font-mono mt-0.5">3-Bot SaaS Execution Environment & Microservices Telemetry</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              ALL BOTS ONLINE
            </span>
          </div>
        </header>

        {/* Dynamic Service Status row */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          
          {/* Card User Bot */}
          <div id="card-user-bot" className="bg-[#12141c]/90 border border-gray-800/80 rounded-xl p-5 hover:border-teal-500/30 transition shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-teal-400 uppercase tracking-widest font-mono p-1 bg-teal-950/40 rounded border border-teal-500/10">BOT 1 (User Panel)</span>
              <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> ACTIVE
              </span>
            </div>
            <h3 className="text-lg font-bold text-white mt-3 font-mono">QuickCVBot</h3>
            <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
              Accepts client messages, triggers multi-step state machines, compiles reportlab PDFs and editable word documents on-disk.
            </p>
          </div>

          {/* Card Admin Bot */}
          <div id="card-admin-bot" className="bg-[#12141c]/90 border border-gray-800/80 rounded-xl p-5 hover:border-teal-500/30 transition shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-teal-400 uppercase tracking-widest font-mono p-1 bg-teal-950/40 rounded border border-teal-500/10">BOT 2 (Admin Panel)</span>
              <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> ACTIVE
              </span>
            </div>
            <h3 className="text-lg font-bold text-white mt-3 font-mono">QuickCVPanelBot</h3>
            <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
              Handles system telemetry statistics reporting, processes mass client broadcasts with analytics, manages credit reserves, and bans.
            </p>
          </div>

          {/* Card Credit Bot */}
          <div id="card-credit-bot" className="bg-[#12141c]/90 border border-gray-800/80 rounded-xl p-5 hover:border-teal-500/30 transition shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-teal-400 uppercase tracking-widest font-mono p-1 bg-teal-950/40 rounded border border-teal-500/10">BOT 3 (Credit Alerts)</span>
              <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> ACTIVE
              </span>
            </div>
            <h3 className="text-lg font-bold text-white mt-3 font-mono">QuickCVCreditBot</h3>
            <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
              Triggers real-time alerts on credit claim rewards, referral milestones, or administrative currency injections.
            </p>
          </div>

        </section>

        {/* Database statistics row */}
        <section className="bg-[#12141c]/90 border border-gray-800/80 rounded-xl p-6 mb-8 shadow-xl">
          <div className="flex items-center gap-2 mb-4">
            <Database size={18} className="text-teal-400" />
            <h4 className="text-sm font-semibold tracking-wide uppercase text-white font-mono">SQLite Core Persistence Aggregates</h4>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-[#0b0c10] p-4 rounded-lg border border-gray-800/60 transition hover:border-slate-800">
              <span className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">Total User Accounts</span>
              <span className="text-xl font-bold text-white mt-1 block font-mono">{stats.totalUsers}</span>
            </div>
            <div className="bg-[#0b0c10] p-4 rounded-lg border border-gray-800/60 transition hover:border-slate-800">
              <span className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">CVs Built & Saved</span>
              <span className="text-xl font-bold text-white mt-1 block font-mono">{stats.resumesDrafted}</span>
            </div>
            <div className="bg-[#0b0c10] p-4 rounded-lg border border-gray-800/60 transition hover:border-slate-800">
              <span className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">Today's Generation Rate</span>
              <span className="text-xl font-bold text-teal-400 mt-1 block font-mono">+{stats.todayDrafts} Built</span>
            </div>
            <div className="bg-[#0b0c10] p-4 rounded-lg border border-gray-800/60 transition hover:border-slate-800">
              <span className="text-[10px] text-slate-500 font-bold uppercase tracking-widest font-mono">Default active model</span>
              <span className="text-xs font-bold text-indigo-400 mt-2 block font-mono truncate">{botStatus.activeModel}</span>
            </div>
          </div>
        </section>

        {/* Command tabs & Terminal log viewer */}
        <section className="bg-[#12141c]/90 border border-gray-800/80 rounded-xl overflow-hidden shadow-xl">
          
          <div className="border-b border-gray-800 bg-[#161924]/60 px-6 py-4 flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-1 bg-[#0b0c10] p-1 rounded-lg border border-gray-800/80">
              <button 
                id="btn-tab-status"
                onClick={() => setActiveTab('status')}
                className={`px-4 py-1.5 text-xs font-semibold rounded-md font-mono transition ${activeTab === 'status' ? 'bg-[#1e2330] text-white border border-gray-700/80 shadow-md' : 'text-slate-400 hover:text-white'}`}
              >
                ⚙️ Engine parameters
              </button>
              <button 
                id="btn-tab-logs"
                onClick={() => setActiveTab('logs')}
                className={`px-4 py-1.5 text-xs font-semibold rounded-md font-mono transition ${activeTab === 'logs' ? 'bg-[#1e2330] text-white border border-gray-700/80 shadow-md' : 'text-slate-400 hover:text-white'}`}
              >
                📜 Live Telemetry Terminal
              </button>
            </div>
            <div className="text-xs font-mono text-slate-500">
              Uptime Code: <span className="text-slate-400">100% stable</span>
            </div>
          </div>

          <div className="p-6">
            
            {activeTab === 'status' && (
              <div id="tab-status-content" className="space-y-6">
                <div>
                  <h3 className="text-base font-bold text-white font-mono flex items-center gap-2">
                    ⚡ Integrated Execution Parameters
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">Unified configurations and database parameters compiled inside standard SQLite schemas</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  
                  <div className="space-y-4">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-teal-400 font-mono">Settings & Seeding</h4>
                    <ul className="text-xs font-mono space-y-2.5 bg-[#0b0c10] border border-gray-800/60 p-4 rounded-lg">
                      <li className="flex justify-between py-1 border-b border-gray-800/40">
                        <span className="text-slate-500">SQLite Database Driver:</span>
                        <span className="text-white">sqlite3</span>
                      </li>
                      <li className="flex justify-between py-1 border-b border-gray-800/40">
                        <span className="text-slate-500">Database Location Path:</span>
                        <span className="text-white">/data/quickcv.db</span>
                      </li>
                      <li className="flex justify-between py-1 border-b border-gray-800/40">
                        <span className="text-slate-500">Schema Table count:</span>
                        <span className="text-white">8 Tables</span>
                      </li>
                      <li className="flex justify-between py-1">
                        <span className="text-slate-500">Render Start Command:</span>
                        <span className="text-teal-400">python main.py</span>
                      </li>
                    </ul>
                  </div>

                  <div className="space-y-4">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-teal-400 font-mono">Credit System Constraints</h4>
                    <ul className="text-xs font-mono space-y-2.5 bg-[#0b0c10] border border-gray-800/60 p-4 rounded-lg">
                      <li className="flex justify-between py-1 border-b border-gray-800/40">
                        <span className="text-slate-500">Initial Registration Credits:</span>
                        <span className="text-emerald-400">2 Credits (Free)</span>
                      </li>
                      <li className="flex justify-between py-1 border-b border-gray-800/40">
                        <span className="text-slate-500">Daily Reward balance claim:</span>
                        <span className="text-emerald-400">+2 Credits Every 24h</span>
                      </li>
                      <li className="flex justify-between py-1 border-b border-gray-800/40">
                        <span className="text-slate-500">Referral Commission:</span>
                        <span className="text-emerald-400">+1 Credit / Join</span>
                      </li>
                      <li className="flex justify-between py-1">
                        <span className="text-slate-500">Resume Compiler Cost:</span>
                        <span className="text-amber-400">1 Credit / generation</span>
                      </li>
                    </ul>
                  </div>

                </div>
              </div>
            )}

            {activeTab === 'logs' && (
              <div id="tab-logs-content" className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-slate-500 uppercase tracking-widest flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-ping"></span>
                    Terminal logging stream (last 20 logs)
                  </span>
                  <button 
                     onClick={() => setLogs(prev => [
                       { time: new Date().toLocaleTimeString(), level: 'INFO', category: 'MANUAL_REFRESH', message: 'Flushed diagnostic sockets.' },
                       ...prev
                     ])}
                     className="text-2xs font-mono bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold px-2 py-1 rounded flex items-center gap-1 border border-slate-700 transition"
                  >
                     <RefreshCw size={10} /> FORCE RE-SYNC
                  </button>
                </div>

                <div className="bg-[#0b0c10] border border-gray-800/80 rounded-lg p-4 font-mono text-xs overflow-y-auto max-h-80 space-y-2 select-text">
                  {logs.map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 hover:bg-gray-850 py-0.5 px-1 rounded transition">
                      <span className="text-slate-600">[{log.time}]</span>
                      <span className="text-slate-400 font-bold">[{log.level}]</span>
                      <span className="text-teal-400">[{log.category}]</span>
                      <span className="text-slate-300 flex-1">{log.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>

        </section>

      </div>
    </div>
  );
}
