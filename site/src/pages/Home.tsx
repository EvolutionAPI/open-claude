import { useEffect, useRef, useState, useCallback } from "react";
import { motion, useInView, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Terminal, Bot, BrainCircuit, Calendar, LayoutDashboard,
  Workflow, Database, Activity, Code, Clock, Zap, Menu,
  Copy, Check, X, FileText, GitBranch, Cpu, MessageSquare, Shield, Layers
} from "lucide-react";
import {
  SiGooglecalendar, SiGmail, SiGithub, SiLinear, SiDiscord,
  SiTelegram, SiStripe, SiFathom, SiTodoist, SiYoutube,
  SiInstagram, SiCanva, SiNotion, SiObsidian
} from "react-icons/si";

import MainLogo from "@assets/logo.webp";
import EvoNexusLogo from "@assets/EVO_NEXUS.webp";
import printOverview from "@assets/print-overview.webp";
import printAgents from "@assets/print-agents.webp";
import printIntegrations from "@assets/print-integrations.webp";
import printCosts from "@assets/print-costs.webp";

const FadeIn = ({ children, delay = 0, className = "" }: { children: React.ReactNode, delay?: number, className?: string }) => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 20 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
};

export default function Home() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [copied, setCopied] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [lightboxImg, setLightboxImg] = useState<string | null>(null);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (lightboxImg) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [lightboxImg]);

  const copyCode = useCallback(() => {
    navigator.clipboard.writeText(`npx @evoapi/evo-nexus`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, []);

  const GITHUB_URL = "https://github.com/EvolutionAPI/evo-nexus";
  const DOCS_URL = "/docs";

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMobileMenuOpen(false);
  };

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-primary/30 selection:text-primary relative overflow-hidden font-sans">
      {/* Background elements */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay"></div>
        <div className="absolute top-0 inset-x-0 h-[500px] bg-gradient-to-b from-primary/10 to-transparent opacity-30 blur-3xl"></div>
        <div className="absolute top-1/4 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-primary/20 to-transparent"></div>
        <div className="absolute top-2/4 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-primary/10 to-transparent"></div>
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#34405422_1px,transparent_1px),linear-gradient(to_bottom,#34405422_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]"></div>
      </div>

      {/* Lightbox Modal */}
      <AnimatePresence>
        {lightboxImg && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black/90 backdrop-blur-sm flex items-center justify-center p-4 cursor-pointer"
            onClick={() => setLightboxImg(null)}
            data-testid="lightbox-overlay"
          >
            <button
              className="absolute top-6 right-6 text-white/70 hover:text-white transition-colors z-10"
              onClick={() => setLightboxImg(null)}
              data-testid="lightbox-close"
            >
              <X className="w-8 h-8" />
            </button>
            <motion.img
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              src={lightboxImg}
              alt="Screenshot"
              className="max-w-[90vw] max-h-[90vh] object-contain rounded-xl shadow-2xl border border-border"
              onClick={(e) => e.stopPropagation()}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Navigation */}
      <nav className={`fixed top-0 w-full z-50 transition-all duration-300 border-b ${isScrolled ? 'bg-background/80 backdrop-blur-md border-border' : 'bg-transparent border-transparent'}`}>
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src={EvoNexusLogo} alt="EvoNexus" className="h-8" />
          </div>

          <div className="hidden md:flex items-center gap-4">
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground transition-colors text-sm font-medium" data-testid="link-github">GitHub</a>
            <a href={DOCS_URL} className="text-muted-foreground hover:text-foreground transition-colors text-sm font-medium" data-testid="link-docs">Docs</a>
            <Button
              className="bg-primary text-primary-foreground hover:bg-primary/90 font-bold shadow-[0_0_15px_rgba(0,255,167,0.3)]"
              onClick={() => scrollTo("quickstart")}
              data-testid="button-get-started-nav"
            >
              Get Started
            </Button>
          </div>

          <button className="md:hidden text-foreground" onClick={() => setMobileMenuOpen(!mobileMenuOpen)} data-testid="button-mobile-menu">
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile menu */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="md:hidden overflow-hidden bg-background/95 backdrop-blur-md border-b border-border"
            >
              <div className="flex flex-col gap-4 px-6 py-6">
                <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="text-foreground font-medium" onClick={() => setMobileMenuOpen(false)}>GitHub</a>
                <a href={DOCS_URL} className="text-foreground font-medium" onClick={() => setMobileMenuOpen(false)}>Docs</a>
                <Button
                  className="bg-primary text-primary-foreground hover:bg-primary/90 font-bold w-full"
                  onClick={() => scrollTo("quickstart")}
                >
                  Get Started
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      <main className="relative z-10 pt-32 pb-24 flex flex-col gap-32">
        {/* Hero Section */}
        <section className="max-w-7xl mx-auto px-6 text-center flex flex-col items-center">
          <FadeIn>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium mb-8">
              <Zap className="w-4 h-4" />
              <span>v{__APP_VERSION__} is now live</span>
            </div>
            <h1 className="text-5xl md:text-7xl font-bold tracking-tighter max-w-4xl mx-auto leading-tight mb-6">
              The open source operating system for <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-emerald-300">AI-powered businesses</span>
            </h1>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-8 leading-relaxed">
              A markdown-first multi-agent operating layer that runs on Anthropic's Claude CLI by default — or on OpenAI, Gemini, Bedrock, Vertex, or OpenRouter via OpenClaude. 38 specialized agents (17 business + 21 engineering), 150+ skills, automated routines, channels, and a web dashboard — all in one command.
            </p>

            {/* Social proof numbers */}
            <div className="flex flex-wrap justify-center gap-4 mb-10">
              {[
                { value: "17,000+", label: "Community members" },
                { value: "38", label: "AI Agents" },
                { value: "150+", label: "Skills" },
                { value: "18", label: "Integrations" },
              ].map((stat, i) => (
                <div key={i} className="flex items-center gap-2 px-4 py-2 rounded-full bg-card border border-border text-sm">
                  <span className="font-bold text-primary">{stat.value}</span>
                  <span className="text-muted-foreground">{stat.label}</span>
                </div>
              ))}
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
              <Button
                size="lg"
                className="w-full sm:w-auto bg-primary text-primary-foreground hover:bg-primary/90 font-bold text-lg px-8 h-14 shadow-[0_0_20px_rgba(0,255,167,0.4)]"
                onClick={() => scrollTo("quickstart")}
                data-testid="button-get-started-hero"
              >
                Get Started — it's free
              </Button>
              <Button size="lg" variant="outline" className="w-full sm:w-auto border-border hover:bg-muted text-foreground font-medium text-lg px-8 h-14" data-testid="button-github-hero" asChild>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                  <SiGithub className="w-5 h-5 mr-2" />
                  View on GitHub
                </a>
              </Button>
            </div>
          </FadeIn>

          <FadeIn delay={0.2} className="w-full max-w-3xl mx-auto text-left">
            <div className="rounded-xl overflow-hidden bg-[#0a0f18] border border-border shadow-2xl relative">
              <div className="absolute top-0 inset-x-0 h-8 bg-muted flex items-center px-4 gap-2 border-b border-border">
                <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
                <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
                <div className="mx-auto text-xs text-muted-foreground font-mono">bash</div>
              </div>
              <div className="p-6 pt-12 font-mono text-sm leading-relaxed text-gray-300">
                <div className="flex gap-2"><span className="text-primary">$</span> <span>npx @evoapi/evo-nexus</span></div>
                <div className="text-emerald-400 mt-2">&#10003; Claude Code CLI detected</div>
                <div className="text-emerald-400">&#10003; Dependencies installed</div>
                <div className="text-emerald-400">&#10003; Dashboard built</div>
                <div className="text-blue-400 mt-2 font-bold">&#8594; Open http://localhost:8080</div>
                <div className="w-2 h-4 bg-primary animate-pulse mt-2"></div>
              </div>
            </div>
          </FadeIn>
        </section>

        {/* Screenshots Grid */}
        <section className="max-w-7xl mx-auto px-6">
          <FadeIn>
            <div className="text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">Command center for your AI team</h2>
              <p className="text-muted-foreground text-lg max-w-2xl mx-auto">Everything you need to monitor, manage, and collaborate with your AI agents.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {[
                { title: "Overview Dashboard", img: printOverview },
                { title: "Multi Agents", img: printAgents },
                { title: "Integrations", img: printIntegrations },
                { title: "Cost Tracking", img: printCosts },
              ].map((item, i) => (
                <div
                  key={i}
                  className="group relative rounded-xl border border-border bg-card overflow-hidden shadow-lg transition-all hover:border-primary/50 hover:shadow-[0_0_30px_rgba(0,255,167,0.1)] cursor-pointer"
                  onClick={() => setLightboxImg(item.img)}
                  data-testid={`screenshot-${i}`}
                >
                  <div className="overflow-hidden bg-muted/50 p-3">
                    <img src={item.img} alt={item.title} className="w-full h-auto rounded-lg border border-border/50 shadow-sm group-hover:scale-[1.02] transition-transform duration-300" />
                  </div>
                  <div className="p-4 bg-card border-t border-border flex items-center justify-between">
                    <h3 className="font-semibold text-lg">{item.title}</h3>
                    <span className="text-xs text-muted-foreground group-hover:text-primary transition-colors">Click to expand</span>
                  </div>
                </div>
              ))}
            </div>
          </FadeIn>
        </section>

        {/* Features Grid */}
        <section className="max-w-7xl mx-auto px-6">
          <FadeIn>
            <div className="text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">Everything included. Zero lock-in.</h2>
              <p className="text-muted-foreground text-lg max-w-2xl mx-auto">EvoNexus comes with a complete suite of tools out of the box.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
              {[
                { icon: Bot, title: "38 Specialized Agents", desc: "Two ortogonal layers — Business (17): Ops, Finance, Projects, Community, Social, Strategy, Sales, Marketing, HR, CS, Legal, Product, Data, Courses, Personal, Knowledge, Learning Retention. Engineering (21): Architect, Planner, Executor, Code Reviewer, Debugger, Security, Tester, Verifier, Designer, and more." },
                { icon: BrainCircuit, title: "150+ Skills", desc: "Business skills (fin-, social-, mkt-, hr-, legal-...) plus 25 dev-* engineering skills (autopilot, plan, ralplan, verify, ultraqa, trace...)" },
                { icon: Clock, title: "Automated Routines", desc: "Morning briefing to monthly close, running on schedule automatically" },
                { icon: LayoutDashboard, title: "Web Dashboard", desc: "React + Flask with auth, roles, terminal, reports, service management" },
                { icon: Workflow, title: "18 Integrations", desc: "Gmail, Calendar, GitHub, Linear, Discord, Stripe, Evolution API, Evolution Go, Evo CRM, and more" },
                { icon: MessageSquare, title: "Channels", desc: "Bidirectional chat via Telegram, Discord, and iMessage — talk to Claude from your phone" },
                { icon: Database, title: "Persistent Memory", desc: "Two-tier system that remembers context across conversations and sessions" },
                { icon: Activity, title: "Agent Teams", desc: "Parallel multi-agent execution for faster consolidation routines (experimental)" },
                { icon: Zap, title: "Scheduled Tasks", desc: "One-off actions at a specific date/time — schedule a skill, prompt, or script" },
                { icon: Code, title: "100% Open Source", desc: "MIT License, fork it, customize it, own your entire AI infrastructure." },
              ].map((feature, i) => (
                <Card key={i} className="bg-card border-border hover:border-primary/30 transition-colors">
                  <CardContent className="p-6">
                    <feature.icon className="w-10 h-10 text-primary mb-4" />
                    <h3 className="text-xl font-bold mb-2">{feature.title}</h3>
                    <p className="text-muted-foreground">{feature.desc}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </FadeIn>
        </section>

        {/* Why EvoNexus? */}
        <section className="max-w-7xl mx-auto px-6">
          <FadeIn>
            <div className="text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">Why EvoNexus?</h2>
              <p className="text-muted-foreground text-lg max-w-2xl mx-auto">A markdown-first operating layer that runs on any LLM you choose — Claude, GPT, Gemini, Bedrock, Vertex, or OpenRouter. Here's what makes it different.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[
                { icon: FileText, title: "Markdown-First Agents", desc: "Agents are plain `.md` files with system prompts. No SDK, no plugin runtime, no compile step. Drop a file in .claude/agents/ and it's live." },
                { icon: BrainCircuit, title: "Skills as Instructions", desc: "150+ reusable capabilities across finance, community, social, engineering, data, legal, HR, ops, product, CS \u2014 each one a markdown instruction set. Add, edit, or remove by editing text." },
                { icon: Layers, title: "Multi-Provider, No Lock-In", desc: "Default runs on Anthropic's native claude CLI, or swap to OpenRouter, OpenAI, Gemini, Bedrock, or Vertex AI via OpenClaude. One click in the Providers page \u2014 no code changes. Your keys, your model choice." },
                { icon: Cpu, title: "MCP Integrations", desc: "Model Context Protocol connects agents to Google Calendar, Gmail, GitHub, Linear, Telegram, Canva, Notion, and more \u2014 with a standardized interface. First-class support built in." },
                { icon: Terminal, title: "Slash Commands", desc: "Type /clawdia, /flux, /pulse, or /apex to activate agents instantly. Natural command interface directly in the terminal \u2014 no menus, no forms." },
                { icon: Database, title: "Persistent Memory", desc: "Two-tier memory: CLAUDE.md for working state, per-agent memory/ for long-term context. Survives across sessions. Your agents remember who you are, what you're working on, and what's been decided." },
              ].map((item, i) => (
                <div key={i} className="group relative p-6 rounded-xl border border-border bg-card/50 hover:bg-card hover:border-primary/30 transition-all">
                  <div className="w-12 h-12 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center mb-4 group-hover:shadow-[0_0_15px_rgba(0,255,167,0.2)] transition-shadow">
                    <item.icon className="w-6 h-6 text-primary" />
                  </div>
                  <h3 className="text-lg font-bold mb-2">{item.title}</h3>
                  <p className="text-muted-foreground text-sm leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>
          </FadeIn>
        </section>

        {/* How It Works */}
        <section className="max-w-7xl mx-auto px-6 py-12 relative">
          <FadeIn>
            <div className="text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">From zero to AI ops in minutes</h2>
            </div>

            <div className="flex flex-col md:flex-row gap-8 relative">
              <div className="hidden md:block absolute top-12 left-[10%] right-[10%] h-[2px] bg-border z-0"></div>

              {[
                { step: 1, title: "Install", code: "npx @evoapi/evo-nexus", desc: "CLI wizard configures everything" },
                { step: 2, title: "Start Dashboard", code: "make dashboard-app", desc: "Web UI with admin setup, scheduler included" },
                { step: 3, title: "Use Your Agents", code: "Say 'good morning'", desc: "Your AI team takes over your routines" },
              ].map((item, i) => (
                <div key={i} className="flex-1 flex flex-col items-center text-center relative z-10">
                  <div className="w-24 h-24 rounded-full bg-card border-2 border-primary/50 flex items-center justify-center text-3xl font-bold text-primary mb-6 shadow-[0_0_20px_rgba(0,255,167,0.2)]">
                    {item.step}
                  </div>
                  <h3 className="text-xl font-bold mb-2">{item.title}</h3>
                  <div className="bg-muted px-3 py-1 rounded text-sm font-mono text-primary mb-3">
                    {item.code}
                  </div>
                  <p className="text-muted-foreground">{item.desc}</p>
                </div>
              ))}
            </div>
          </FadeIn>
        </section>

        {/* Agents Showcase */}
        <section className="py-12 bg-muted/30 border-y border-border">
          <div className="max-w-7xl mx-auto px-6 mb-12">
            <FadeIn>
              <h2 className="text-3xl md:text-4xl font-bold mb-4">Meet your new team</h2>
              <p className="text-muted-foreground text-lg">38 specialized agents ready to handle your operations and your code — 17 business agents + 21 engineering agents.</p>
            </FadeIn>
          </div>

          <div className="max-w-7xl mx-auto px-6 space-y-12">
            {/* Business Layer */}
            <div>
              <div className="mb-6 flex items-center gap-3">
                <h3 className="text-xl md:text-2xl font-bold">Business Layer</h3>
                <span className="text-xs font-medium px-2 py-1 rounded bg-primary/10 text-primary border border-primary/30">17 agents</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {[
                  { name: "Clawdia", cmd: "/clawdia-assistant", role: "Ops", desc: "agenda, emails, tasks", color: "text-emerald-400" },
                  { name: "Flux", cmd: "/flux-finance", role: "Finance", desc: "Stripe, ERP, cash flow", color: "text-blue-400" },
                  { name: "Atlas", cmd: "/atlas-project", role: "Projects", desc: "GitHub, Linear, sprints", color: "text-purple-400" },
                  { name: "Pulse", cmd: "/pulse-community", role: "Community", desc: "Discord, WhatsApp", color: "text-pink-400" },
                  { name: "Pixel", cmd: "/pixel-social-media", role: "Social", desc: "content, analytics", color: "text-orange-400" },
                  { name: "Sage", cmd: "/sage-strategy", role: "Strategy", desc: "OKRs, roadmap", color: "text-cyan-400" },
                  { name: "Nex", cmd: "/nex-sales", role: "Sales", desc: "pipeline, proposals", color: "text-yellow-400" },
                  { name: "Mentor", cmd: "/mentor-courses", role: "Courses", desc: "learning paths", color: "text-indigo-400" },
                  { name: "Kai", cmd: "/kai-personal-assistant", role: "Personal", desc: "health, habits", color: "text-rose-400" },
                  { name: "Oracle", cmd: "/oracle", role: "Knowledge", desc: "docs, how-to, config", color: "text-amber-400" },
                  { name: "Mako", cmd: "/mako-marketing", role: "Marketing", desc: "campaigns, SEO, brand", color: "text-orange-500" },
                  { name: "Aria", cmd: "/aria-hr", role: "HR", desc: "recruiting, onboarding", color: "text-pink-500" },
                  { name: "Zara", cmd: "/zara-cs", role: "CS", desc: "triage, escalation", color: "text-teal-400" },
                  { name: "Lex", cmd: "/lex-legal", role: "Legal", desc: "contracts, compliance", color: "text-violet-400" },
                  { name: "Nova", cmd: "/nova-product", role: "Product", desc: "specs, roadmaps", color: "text-yellow-300" },
                  { name: "Dex", cmd: "/dex-data", role: "Data", desc: "analysis, dashboards", color: "text-sky-400" },
                  { name: "Lumen", cmd: "/lumen-learning", role: "Learning", desc: "spaced repetition, quizzes", color: "text-yellow-400" },
                ].map((agent, i) => (
                  <div key={i} className="bg-card border border-border rounded-xl p-6 hover:border-primary/50 transition-colors" data-testid={`agent-card-${agent.name.toLowerCase()}`}>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className={`text-2xl font-bold ${agent.color}`}>{agent.name}</h3>
                      <span className="text-xs font-medium px-2 py-1 rounded bg-secondary/20 text-secondary-foreground border border-secondary/30">{agent.role}</span>
                    </div>
                    <div className="font-mono text-primary text-sm mb-3 bg-primary/10 inline-block px-2 py-1 rounded">
                      {agent.cmd}
                    </div>
                    <p className="text-muted-foreground">{agent.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Engineering Layer */}
            <div>
              <div className="mb-6 flex items-center gap-3 flex-wrap">
                <h3 className="text-xl md:text-2xl font-bold">Engineering Layer</h3>
                <span className="text-xs font-medium px-2 py-1 rounded bg-primary/10 text-primary border border-primary/30">21 agents</span>
                <span className="text-xs text-muted-foreground">19 derived from <a href="https://github.com/yeachan-heo/oh-my-claudecode" className="underline hover:text-primary" target="_blank" rel="noopener noreferrer">oh-my-claudecode</a> (MIT, by Yeachan Heo) + 2 native</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {[
                  { name: "Apex", cmd: "/apex-architect", role: "Architect", desc: "design, debug, tradeoffs (read-only)", color: "text-purple-400" },
                  { name: "Echo", cmd: "/echo-analyst", role: "Analyst", desc: "discovery, gap analysis (read-only)", color: "text-pink-400" },
                  { name: "Compass", cmd: "/compass-planner", role: "Planner", desc: "3-6 step interview-driven plans", color: "text-blue-400" },
                  { name: "Raven", cmd: "/raven-critic", role: "Critic", desc: "multi-perspective review (read-only)", color: "text-red-400" },
                  { name: "Bolt", cmd: "/bolt-executor", role: "Executor", desc: "smallest viable diff implementation", color: "text-yellow-400" },
                  { name: "Hawk", cmd: "/hawk-debugger", role: "Debugger", desc: "root cause + minimal fix", color: "text-orange-400" },
                  { name: "Lens", cmd: "/lens-reviewer", role: "Code Review", desc: "OWASP, SOLID, severity (read-only)", color: "text-red-500" },
                  { name: "Zen", cmd: "/zen-simplifier", role: "Simplifier", desc: "deslop without behavior change", color: "text-green-400" },
                  { name: "Vault", cmd: "/vault-security", role: "Security", desc: "OWASP Top 10, secrets (read-only)", color: "text-red-300" },
                  { name: "Grid", cmd: "/grid-tester", role: "Test Engineer", desc: "TDD, pyramid, flaky diagnosis", color: "text-blue-300" },
                  { name: "Probe", cmd: "/probe-qa", role: "QA Tester", desc: "interactive tmux sessions", color: "text-orange-300" },
                  { name: "Oath", cmd: "/oath-verifier", role: "Verifier", desc: "evidence-based completion (read-only)", color: "text-emerald-400" },
                  { name: "Trail", cmd: "/trail-tracer", role: "Tracer", desc: "competing hypotheses, evidence ranks", color: "text-yellow-300" },
                  { name: "Scout", cmd: "/scout-explorer", role: "Explorer", desc: "fast parallel codebase search (haiku)", color: "text-cyan-400" },
                  { name: "Flow", cmd: "/flow-git", role: "Git Master", desc: "atomic commits, safe rebase", color: "text-orange-500" },
                  { name: "Scroll", cmd: "/scroll-docs", role: "Doc Specialist", desc: "external SDK/API docs (read-only)", color: "text-blue-500" },
                  { name: "Quill", cmd: "/quill-writer", role: "Writer", desc: "tested technical docs (haiku)", color: "text-cyan-300" },
                  { name: "Canvas", cmd: "/canvas-designer", role: "Designer", desc: "production-grade UI/UX", color: "text-pink-500" },
                  { name: "Prism", cmd: "/prism-scientist", role: "Scientist", desc: "formal statistical analysis", color: "text-purple-300" },
                  { name: "Helm", cmd: "/helm-conductor", role: "Conductor", desc: "cycle orchestration + sprint sequencing (native)", color: "text-teal-400" },
                  { name: "Mirror", cmd: "/mirror-retro", role: "Retrospective", desc: "blameless lessons + memory updates (native)", color: "text-slate-300" },
                ].map((agent, i) => (
                  <div key={i} className="bg-card border border-border rounded-xl p-6 hover:border-primary/50 transition-colors" data-testid={`agent-card-${agent.name.toLowerCase()}`}>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className={`text-2xl font-bold ${agent.color}`}>{agent.name}</h3>
                      <span className="text-xs font-medium px-2 py-1 rounded bg-secondary/20 text-secondary-foreground border border-secondary/30">{agent.role}</span>
                    </div>
                    <div className="font-mono text-primary text-sm mb-3 bg-primary/10 inline-block px-2 py-1 rounded">
                      {agent.cmd}
                    </div>
                    <p className="text-muted-foreground">{agent.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Integrations Bar */}
        <section className="max-w-7xl mx-auto px-6 text-center">
          <FadeIn>
            <p className="text-sm font-bold tracking-widest text-muted-foreground uppercase mb-8">Connects with everything you use</p>
            <div className="flex flex-wrap justify-center gap-8 md:gap-12 opacity-60 hover:opacity-100 transition-all duration-500">
              <SiGooglecalendar className="w-8 h-8 hover:text-blue-500 transition-colors" />
              <SiGmail className="w-8 h-8 hover:text-red-500 transition-colors" />
              <SiGithub className="w-8 h-8 hover:text-white transition-colors" />
              <SiLinear className="w-8 h-8 hover:text-purple-500 transition-colors" />
              <SiDiscord className="w-8 h-8 hover:text-indigo-400 transition-colors" />
              <SiTelegram className="w-8 h-8 hover:text-blue-400 transition-colors" />
              <SiStripe className="w-8 h-8 hover:text-indigo-500 transition-colors" />
              <SiTodoist className="w-8 h-8 hover:text-red-500 transition-colors" />
              <SiYoutube className="w-8 h-8 hover:text-red-600 transition-colors" />
              <SiInstagram className="w-8 h-8 hover:text-pink-500 transition-colors" />
              <SiFathom className="w-8 h-8 hover:text-blue-600 transition-colors" />
              <SiCanva className="w-8 h-8 hover:text-blue-500 transition-colors" />
              <SiNotion className="w-8 h-8 hover:text-white transition-colors" />
              <SiObsidian className="w-8 h-8 hover:text-purple-400 transition-colors" />
              <span title="Evolution API"><MessageSquare className="w-8 h-8 hover:text-emerald-400 transition-colors" /></span>
              <span title="Evolution Go"><GitBranch className="w-8 h-8 hover:text-emerald-400 transition-colors" /></span>
              <span title="Evo CRM"><Database className="w-8 h-8 hover:text-emerald-400 transition-colors" /></span>
            </div>
          </FadeIn>
        </section>

        {/* Social Proof */}
        <section className="max-w-4xl mx-auto px-6 py-12">
          <FadeIn>
            <div className="relative bg-card/50 border border-border rounded-2xl p-8 md:p-12">
              <div className="absolute -top-6 left-8 text-8xl text-primary/20 font-serif leading-none select-none">&ldquo;</div>
              <blockquote className="text-xl md:text-2xl font-medium leading-relaxed text-center relative z-10 mb-8">
                Evolution Foundation runs their entire operation on EvoNexus — from morning briefings to monthly financial close, community monitoring across 17,000+ developers, and social media analytics.
              </blockquote>
              <div className="flex items-center justify-center gap-4">
                <img src={MainLogo} alt="Evolution Foundation" className="h-10" />
                <div className="text-left">
                  <div className="font-bold">Evolution Foundation</div>
                  <div className="text-sm text-primary">Creators of EvoNexus</div>
                </div>
              </div>
            </div>
          </FadeIn>
        </section>

        {/* Quick Start */}
        <section id="quickstart" className="max-w-4xl mx-auto px-6 w-full">
          <FadeIn>
            <div className="text-center mb-8">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">Start in 60 seconds</h2>
              <p className="text-muted-foreground text-lg">One command. That's all it takes.</p>
            </div>

            <div className="relative bg-[#0a0f18] rounded-xl border border-border overflow-hidden shadow-2xl">
              <div className="flex items-center justify-between px-4 h-10 bg-muted border-b border-border">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
                </div>
                <span className="text-xs text-muted-foreground font-mono">terminal</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-muted-foreground hover:text-foreground hover:bg-muted h-7 w-7"
                  onClick={copyCode}
                  data-testid="button-copy-code"
                >
                  {copied ? <Check className="w-4 h-4 text-primary" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
              <div className="p-6 md:p-8 font-mono text-base md:text-lg leading-loose">
                <div className="flex gap-3"><span className="text-primary select-none">$</span> <span className="text-gray-300"><span className="text-blue-400">npx</span> @evoapi/evo-nexus</span></div>
                <div className="mt-4 text-muted-foreground text-sm"># Or manually: git clone + make setup + make dashboard-app</div>
              </div>
            </div>

            <div className="text-center mt-8">
              <Button size="lg" className="bg-primary text-primary-foreground hover:bg-primary/90 font-bold text-lg px-10 h-14 shadow-[0_0_20px_rgba(0,255,167,0.4)]" data-testid="button-get-started-bottom" asChild>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                  Get Started Now
                </a>
              </Button>
            </div>
          </FadeIn>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-background pt-16 pb-8 relative">
        <div className="absolute bottom-0 left-0 w-full h-[2px] bg-primary"></div>
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-12 mb-12">
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <img src={MainLogo} alt="Evolution Foundation" className="h-8" />
              </div>
              <p className="text-muted-foreground text-sm">An Evolution Foundation project.</p>
            </div>

            <div className="flex flex-col md:items-center gap-4">
              <h4 className="font-bold mb-2">Links</h4>
              <div className="flex flex-wrap gap-6">
                <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="text-sm text-muted-foreground hover:text-primary transition-colors" data-testid="link-footer-github">GitHub</a>
                <a href={DOCS_URL} className="text-sm text-muted-foreground hover:text-primary transition-colors" data-testid="link-footer-docs">Documentation</a>
                <a href={`${GITHUB_URL}/blob/main/CONTRIBUTING.md`} target="_blank" rel="noreferrer" className="text-sm text-muted-foreground hover:text-primary transition-colors" data-testid="link-footer-contributing">Contributing</a>
                <a href={`${GITHUB_URL}/blob/main/CHANGELOG.md`} target="_blank" rel="noreferrer" className="text-sm text-muted-foreground hover:text-primary transition-colors" data-testid="link-footer-changelog">Changelog</a>
              </div>
            </div>

            <div className="flex flex-col md:items-end gap-4 text-sm text-muted-foreground">
              <p>Unofficial toolkit for Claude Code — not affiliated with Anthropic</p>
              <div className="px-2 py-1 bg-muted rounded border border-border text-xs font-mono">
                MIT License
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
