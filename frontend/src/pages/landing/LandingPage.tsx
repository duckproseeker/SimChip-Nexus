import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FiArrowRight as ArrowRight, FiBox as Boxes, FiCpu as Cpu, FiMenu as Menu, FiMonitor as MonitorPlay, FiServer as Server, FiShare2 as Network, FiX as X } from "react-icons/fi";
import "./landing.css";

const logoMarkSrc = "/media/simchip-nexus-mark.svg";
const heroVideoSrc = "/media/hero-carla-loop.mp4";
const heroPosterSrc = "/media/hero-carla-poster.jpg";
const architectureVideoSrc = "/media/skyFlow.mp4";
const ctaBackgroundSrc = "/media/cta-flow-bg.png";
const workflowBackgroundSrc = "/media/workflow-road-flow.png";
const objectiveParticleIndexes = Array.from({ length: 10 }, (_, index) => index + 1);
const architectureFlowParticles = Array.from({ length: 4 }, (_, index) => index + 1);
const ctaFlowParticles = Array.from({ length: 14 }, (_, index) => index + 1);
const workflowFlowParticles = Array.from({ length: 18 }, (_, index) => index + 1);

// --- Navigation Bar ---
const Navbar = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 50);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <>
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 px-6 lg:px-12 flex items-center justify-between ${
          isScrolled ? "py-4 liquid-nav liquid-nav--scrolled" : "py-6 liquid-nav"
        }`}
      >
        <div className="nav-brand">
          <img 
            src={logoMarkSrc} 
            alt="SimChip Nexus Logo" 
            className="nav-brand__mark" 
          />
          <span className="nav-brand__wordmark">
            <span className="nav-brand__name" data-text="SimChip Nexus">SimChip Nexus</span>
            <span className="nav-brand__signal" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </span>
        </div>
        
        <div className="nav-links hidden md:flex items-center gap-2 text-sm font-medium text-zinc-300 tracking-wide">
          <a href="#goals" className="nav-link">项目愿景</a>
          <a href="#capabilities" className="nav-link">核心能力</a>
          <a href="#architecture" className="nav-link">技术架构</a>
          <a href="#workflow" className="nav-link">测试工作流</a>
        </div>

        <div className="hidden md:block">
          <a
            href="/ui" 
            className="liquid-button liquid-button--primary px-6 py-2.5 text-sm text-white font-semibold"
          >
            进入平台
          </a>
        </div>

        <button 
          className="md:hidden text-white"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
          {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </nav>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-40 bg-[#050508]/95 backdrop-blur-2xl pt-24 px-6 flex flex-col gap-6 md:hidden">
          <a href="#goals" onClick={() => setMobileMenuOpen(false)} className="text-xl text-zinc-300 hover:text-white border-b border-white/10 pb-4">项目愿景</a>
          <a href="#capabilities" onClick={() => setMobileMenuOpen(false)} className="text-xl text-zinc-300 hover:text-white border-b border-white/10 pb-4">核心能力</a>
          <a href="#architecture" onClick={() => setMobileMenuOpen(false)} className="text-xl text-zinc-300 hover:text-white border-b border-white/10 pb-4">技术架构</a>
          <a href="#workflow" onClick={() => setMobileMenuOpen(false)} className="text-xl text-zinc-300 hover:text-white border-b border-white/10 pb-4">测试工作流</a>
          <a
            href="/ui" 
            className="liquid-button liquid-button--primary mt-4 px-6 py-3 text-center text-white font-semibold"
          >
            进入平台
          </a>
        </div>
      )}
    </>
  );
};

// --- Animated Dynamic Background ---
const AnimatedBackground = () => {
  const [videoReady, setVideoReady] = useState(false);

  return (
    <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden bg-[#050508]">
      <video
        aria-hidden="true"
        autoPlay
        className={`hero-video-layer ${videoReady ? "hero-video-layer--ready" : ""}`}
        loop
        muted
        onCanPlay={() => setVideoReady(true)}
        playsInline
        poster={heroPosterSrc}
        preload="auto"
      >
        <source src={heroVideoSrc} type="video/mp4" />
      </video>

      <div
        className={`hero-simulation-fallback ${videoReady ? "hero-simulation-fallback--dimmed" : ""}`}
        aria-hidden="true"
      >
        <div className="hero-road-grid" />
        <div className="hero-lane hero-lane--left" />
        <div className="hero-lane hero-lane--right" />
        <div className="hero-scanline hero-scanline--one" />
        <div className="hero-scanline hero-scanline--two" />
        <div className="hero-data-path hero-data-path--one" />
        <div className="hero-data-path hero-data-path--two" />
        <div className="hero-node hero-node--host" />
        <div className="hero-node hero-node--gateway" />
        <div className="hero-node hero-node--dut" />
      </div>

      <div className="hero-video-shade" aria-hidden="true" />
      <div className="hero-grid-overlay" aria-hidden="true" />
    </div>
  );
};

// --- Section 1: Hero ---
const HeroSection = () => {
  return (
    <section className="relative min-h-screen flex items-center justify-center pt-28 pb-16 px-6 z-10 overflow-hidden">
      <AnimatedBackground />

      <div className="relative z-10 w-full max-w-7xl mx-auto flex flex-col items-center text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="mb-8"
        >
          <div className="liquid-pill inline-flex items-center gap-2 px-4 py-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-xs font-mono text-cyan-50 tracking-widest uppercase">Research Project / Prototype</span>
          </div>
        </motion.div>

        <motion.h1 
          className="max-w-full text-[2.65rem] sm:text-5xl md:text-7xl lg:text-8xl font-bold tracking-normal text-white mb-6 leading-[1.08]"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.1, ease: "easeOut" }}
        >
          SimChip Nexus<br />
          <span className="text-[2.2rem] sm:text-4xl md:text-6xl lg:text-7xl mt-4 block text-transparent bg-clip-text bg-gradient-to-r from-cyan-200 via-sky-100 to-blue-300">芯境智测平台</span>
        </motion.h1>

        <motion.p 
          className="max-w-2xl mx-auto text-base md:text-xl text-zinc-300 mb-12 leading-relaxed font-light"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
        >
          面向自动驾驶域控制器，提供结合 CARLA 闭环仿真与硬件在环 (HIL) 测试的端到端性能评估基准。
        </motion.p>

        <motion.div 
          className="flex flex-col sm:flex-row items-center justify-center gap-6 w-full max-w-md sm:max-w-none sm:w-auto"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3, ease: "easeOut" }}
        >
          <a
            href="/ui"
            className="liquid-button liquid-button--primary w-full sm:w-auto px-10 py-4 text-white font-semibold flex items-center justify-center gap-2"
          >
            进入平台
            <ArrowRight className="w-4 h-4" />
          </a>
          
          <a 
            href="#architecture"
            className="liquid-button w-full sm:w-auto px-10 py-4 text-zinc-200 hover:text-white font-medium text-center"
          >
            查看技术架构
          </a>
        </motion.div>
      </div>

      {/* Scroll indicator */}
      <motion.div 
        className="absolute z-10 bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-zinc-400"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1, duration: 1 }}
      >
        <span className="text-xs font-mono tracking-widest uppercase">向下滚动</span>
        <motion.div 
          animate={{ y: [0, 8, 0] }} 
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        >
          <div className="w-[1px] h-12 bg-gradient-to-b from-cyan-400 to-transparent" />
        </motion.div>
      </motion.div>
    </section>
  );
};

// --- Section 2: Goals & Context ---
const ObjectivesSection = () => {
  return (
    <section id="goals" className="py-32 px-6 relative z-10">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16">
          <motion.div 
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.7 }}
            className="objective-card liquid-glass space-y-8 p-10 md:p-14 relative overflow-hidden"
          >
            <div
              className="objective-card__media"
              style={{ backgroundImage: "url('/media/objective-limitations.png')" }}
              aria-hidden="true"
            />
            <div className="objective-card__veil objective-card__veil--warning" aria-hidden="true" />
            <div className="objective-card__particles objective-card__particles--warning" aria-hidden="true">
              <span className="objective-flow objective-flow--one" />
              <span className="objective-flow objective-flow--two" />
              {objectiveParticleIndexes.map((index) => (
                <span key={index} className={`objective-particle objective-particle--${index}`} />
              ))}
            </div>
            <div className="relative z-10">
              <div className="text-cyan-400 font-mono text-sm tracking-widest uppercase border-b border-white/10 pb-4 mb-8 inline-block">
                01 // 突破物理限制
              </div>
              <h3 className="text-3xl md:text-4xl font-semibold text-white leading-tight tracking-tight mb-6">
                突破纯软件仿真的<br/>局限性
              </h3>
              <p className="text-zinc-300 text-lg leading-relaxed font-light">
                传统的自动驾驶路测面临着成本高昂、危险性大、长尾场景难以覆盖等问题。而纯软件环境的仿真测试往往脱离了真实物理硬件，无法有效暴露域控制器芯片在算力、延迟、吞吐等方面的实际瓶颈。
              </p>
            </div>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="objective-card liquid-glass space-y-8 p-10 md:p-14 relative overflow-hidden"
          >
             <div
               className="objective-card__media"
               style={{ backgroundImage: "url('/media/objective-hil.png')" }}
               aria-hidden="true"
             />
             <div className="objective-card__veil objective-card__veil--connected" aria-hidden="true" />
             <div className="objective-card__particles objective-card__particles--connected" aria-hidden="true">
               <span className="objective-flow objective-flow--one" />
               <span className="objective-flow objective-flow--two" />
               {objectiveParticleIndexes.map((index) => (
                 <span key={index} className={`objective-particle objective-particle--${index}`} />
               ))}
             </div>
             <div className="relative z-10">
              <div className="text-blue-400 font-mono text-sm tracking-widest uppercase border-b border-white/10 pb-4 mb-8 inline-block">
                02 // 虚实结合
              </div>
              <h3 className="text-3xl md:text-4xl font-semibold text-white leading-tight tracking-tight mb-6">
                构建高保真虚实结合<br/>评估体系
              </h3>
              <p className="text-zinc-300 text-lg leading-relaxed font-light mb-6">
                本项目致力于通过构建高保真的虚拟场景注入网络，将 CARLA 仿真环境与真实的车载算力待测端深度结合，提供一套标准化、可复现的硬件在环 (HIL) 评测基准与可视化平台。
              </p>
              <ul className="space-y-4 pt-4 border-t border-white/5">
                {[
                  "多传感器数据级同步注入",
                  "全链路延迟测量与性能剖析",
                  "异构芯片通用适配架构"
                ].map((item, i) => (
                  <li key={i} className="flex items-center gap-4 text-zinc-200">
                    <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full shadow-[0_0_8px_rgba(6,182,212,0.8)]" />
                    <span className="text-base">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

// --- Section 3: Visual Capability Showcase ---
const showcaseItems = [
  {
    id: "01",
    eyebrow: "Scenario Simulation",
    title: "高保真场景仿真",
    desc: "基于 CARLA 构建可复现的自动驾驶测试场景，将道路、天气、交通参与者与虚拟传感器统一纳入同一条评测链路。",
    image: "/media/showcase-simulation.jpg",
    points: ["多天气与光照组合", "动态车辆与行人行为", "摄像头 / LiDAR / Radar 数据输出"],
    variant: "simulation"
  },
  {
    id: "02",
    eyebrow: "Hardware-in-the-Loop",
    title: "硬件在环闭环测试",
    desc: "将仿真传感器数据按时间戳同步注入车载算力芯片待测端，覆盖从场景生成、数据传输到算法处理的端到端流程。",
    image: "/media/showcase-hil.jpg",
    points: ["网关转发与协议适配", "待测端算法负载运行", "链路延迟与吞吐过程采集"],
    variant: "hil"
  },
  {
    id: "03",
    eyebrow: "Evaluation Report",
    title: "测评结果分析",
    desc: "面向不同车载算力芯片和域控制器输出统一的评估视图，帮助对比算法负载、资源消耗与链路性能表现。",
    image: "/media/showcase-report.jpg",
    points: ["任务结果汇总", "性能分布与异常定位", "报告化输出与复盘"],
    variant: "report"
  }
];

const CapabilitiesSection = () => {
  return (
    <section id="capabilities" className="py-32 px-6 relative z-10 overflow-hidden">
      <div className="max-w-[92rem] mx-auto">
        <div className="mb-14 md:mb-20 max-w-4xl">
          <p className="text-cyan-400 font-mono tracking-widest uppercase text-sm mb-6">PLATFORM CAPABILITY SHOWCASE</p>
          <h2 className="text-4xl md:text-6xl font-bold text-white tracking-normal leading-tight">从仿真场景到测评结论</h2>
        </div>

        <div className="showcase-rail" aria-label="平台核心能力图文展示">
          {showcaseItems.map((item, idx) => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: idx * 0.1, duration: 0.6 }}
              className={`showcase-card showcase-card--${item.variant}`}
            >
              <div
                className="showcase-media"
                style={{ "--showcase-image": `url(${item.image})` } as React.CSSProperties}
              >
                <div className="showcase-media__image" />
                <div className="showcase-dataflow" aria-hidden="true">
                  <span className="showcase-flow-line showcase-flow-line--one" />
                  <span className="showcase-flow-line showcase-flow-line--two" />
                  <span className="showcase-flow-line showcase-flow-line--three" />
                  {Array.from({ length: 8 }).map((_, particleIdx) => (
                    <span
                      key={particleIdx}
                      className={`showcase-particle showcase-particle--${particleIdx + 1}`}
                    />
                  ))}
                </div>
              </div>

              <div className="showcase-copy">
                <div className="showcase-kicker">
                  <span>{item.id}</span>
                  <span>{item.eyebrow}</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
                <ul>
                  {item.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

// --- Section 4: Architecture ---
const architectureLayers = [
  {
    name: "场景仿真层",
    en: "SCENARIO SIMULATION",
    icon: Boxes,
    tone: "scenario",
    items: ["CARLA 仿真引擎", "物理级传感器建模", "OpenSCENARIO 驱动引擎"]
  },
  {
    name: "虚拟传感器中间件层",
    en: "SENSOR MIDDLEWARE",
    icon: Network,
    tone: "sensor",
    items: ["协议转换", "网关注入", "数据格式解包与时间戳对齐"]
  },
  {
    name: "芯片测试层",
    en: "DUT / CHIP TESTING",
    icon: Cpu,
    tone: "chip",
    items: ["车载算力芯片", "感知算法推理", "状态回传代理"]
  },
  {
    name: "评估分析层",
    en: "EVALUATION & ANALYSIS",
    icon: Server,
    tone: "analysis",
    items: ["时延链路分析", "吞吐量计算", "系统资源监控", "结果报告生成"]
  }
];

const ArchitectureSection = () => {
  return (
    <section id="architecture" className="architecture-section py-24 md:py-28 px-6 relative z-10 overflow-hidden">
      <video
        aria-hidden="true"
        autoPlay
        className="architecture-video"
        loop
        muted
        playsInline
        preload="metadata"
      >
        <source src={architectureVideoSrc} type="video/mp4" />
      </video>
      <div className="architecture-video-shade" aria-hidden="true" />
      <div className="architecture-bg architecture-bg--one" aria-hidden="true" />
      <div className="architecture-bg architecture-bg--two" aria-hidden="true" />
      <div className="max-w-7xl mx-auto relative z-10">
        <div className="mb-14 md:mb-16 text-center flex flex-col items-center">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-6 tracking-normal">平台技术架构</h2>
          <p className="text-blue-400 font-mono tracking-widest uppercase text-sm">ARCHITECTURE DESIGN</p>
        </div>

        <div className="architecture-backbone">
          <div className="architecture-spine" aria-hidden="true">
            <span className="architecture-spine__core" />
            {architectureFlowParticles.map((particle) => (
              <span key={particle} className={`architecture-spine__particle architecture-spine__particle--${particle}`} />
            ))}
          </div>

          {architectureLayers.map((layer, idx) => (
            <motion.article
              key={layer.name}
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ delay: idx * 0.1, duration: 0.6 }}
              className={`architecture-layer architecture-layer--${layer.tone}`}
            >
              <div className="architecture-layer__beam architecture-layer__beam--left" aria-hidden="true" />
              <div className="architecture-layer__beam architecture-layer__beam--right" aria-hidden="true" />

              <div className="architecture-module">
                <div className="architecture-module__scan" aria-hidden="true" />
                <div className="architecture-module__meta">
                  <span>0{idx + 1}</span>
                  <span>{layer.en}</span>
                </div>
                <div className="architecture-module__title">
                  <span className="architecture-module__icon">
                    <layer.icon className="w-6 h-6" />
                  </span>
                  <h3>{layer.name}</h3>
                </div>
              </div>

              <div className="architecture-node" aria-hidden="true">
                <span className="architecture-node__ring" />
                <span className="architecture-node__core" />
              </div>

              <div className="architecture-chips">
                {layer.items.map((item) => (
                  <div key={item} className="architecture-chip">
                    <span className="architecture-chip__icon">
                      <Boxes className="w-4 h-4" />
                    </span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
};

// --- Section 5: Workflow ---
const WorkflowSection = () => {
  const steps = [
    {
      id: "01",
      label: "SCENARIO SOURCE",
      title: "CARLA 仿真主机",
      desc: "生成摄像头 / LiDAR / Radar 原始数据",
      tags: ["场景渲染", "传感器流", "原始数据"],
      icon: <MonitorPlay className="w-6 h-6" />
    },
    {
      id: "02",
      label: "SENSOR GATEWAY",
      title: "虚拟传感器注入网关",
      desc: "完成时间戳对齐、数据打包与协议转发",
      tags: ["时间同步", "协议转换", "物理转发"],
      icon: <Network className="w-6 h-6" />
    },
    {
      id: "03",
      label: "DUT RUNTIME",
      title: "车载算力待测端",
      desc: "运行感知 / 规控算法并处理负载",
      tags: ["算法负载", "待测端", "端侧运行"],
      icon: <Cpu className="w-6 h-6" />
    },
    {
      id: "04",
      label: "EVALUATION CONSOLE",
      title: "Web 测评平台",
      desc: "调度执行、汇总日志并输出测评结论",
      tags: ["任务调度", "日志汇总", "结果分析"],
      icon: <Server className="w-6 h-6" />
    },
  ];

  return (
    <section id="workflow" className="workflow-section py-28 px-6 relative z-10 overflow-hidden">
      <div
        className="workflow-media"
        style={{ backgroundImage: `url(${workflowBackgroundSrc})` }}
        aria-hidden="true"
      />
      <div className="workflow-bg workflow-bg--left" aria-hidden="true" />
      <div className="workflow-bg workflow-bg--right" aria-hidden="true" />
      <div className="workflow-stars" aria-hidden="true" />

      <div className="max-w-[92rem] mx-auto relative z-10">
        <div className="mb-14 md:text-center flex flex-col items-center">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-6 tracking-normal">测试工作流</h2>
          <p className="text-cyan-400 font-mono tracking-widest uppercase text-sm">END-TO-END DATA FLOW</p>
        </div>

        <div className="workflow-pipeline">
          <div className="workflow-track" aria-hidden="true">
            <span className="workflow-track__core" />
            <span className="workflow-track__glow" />
            <div className="workflow-track__particles">
              {workflowFlowParticles.map((particle) => (
                <span
                  key={particle}
                  style={{
                    "--delay": `${particle * -0.38}s`,
                    "--size": `${3 + (particle % 4)}px`
                  } as React.CSSProperties}
                />
              ))}
            </div>
          </div>

          <div className="workflow-node-grid">
          {steps.map((step, idx) => (
              <motion.article
                key={step.id}
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.15, duration: 0.5 }}
                className={`workflow-node workflow-node--${idx + 1}`}
              >
                <div className="workflow-node__port" aria-hidden="true" />
                <div className="workflow-node__shell">
                  <span className="workflow-node__scan" aria-hidden="true" />
                  <div className="workflow-node__meta">
                    <span>{step.id}</span>
                    <span>{step.label}</span>
                  </div>
                  <div className="workflow-node__icon">
                    {step.icon}
                  </div>
                  <h4>{step.title}</h4>
                  <p>{step.desc}</p>
                  <div className="workflow-node__tags">
                    {step.tags.map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                  <div className="workflow-node__watermark" aria-hidden="true">{step.id}</div>
                </div>
              </motion.article>
          ))}
          </div>
        </div>
      </div>
    </section>
  );
};

// --- Section 6: Final CTA ---
const FinalCTASection = () => {
  return (
    <section id="launch" className="cta-section px-6 flex items-center justify-center text-center relative z-10 overflow-hidden mt-12">
      <div
        className="cta-flow-media"
        style={{ backgroundImage: `url(${ctaBackgroundSrc})` }}
        aria-hidden="true"
      />
      <div className="cta-flow-shade" aria-hidden="true" />
      <div className="cta-flow-grid" aria-hidden="true" />
      <div className="cta-flow-lines" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="cta-flow-particles" aria-hidden="true">
        {ctaFlowParticles.map((particle) => (
          <span
            key={particle}
            style={{
              "--x": `${(particle * 17) % 100}%`,
              "--y": `${14 + ((particle * 29) % 70)}%`,
              "--delay": `${particle * -0.42}s`,
              "--size": `${2 + (particle % 4)}px`
            } as React.CSSProperties}
          />
        ))}
      </div>

      <div className="cta-content cta-copy max-w-7xl mx-auto w-full">
        <div className="cta-kicker">开始测试</div>
        <h2 className="cta-title text-white mb-8">Ready to Start Testing?</h2>
        <p className="text-zinc-300 mb-12 max-w-2xl mx-auto text-lg font-light leading-relaxed">
          平台核心服务已就绪。进入系统，配置仿真场景并接入您的域控制器节点。
        </p>
        <a
            href="/ui"
          className="liquid-button liquid-button--primary inline-flex items-center justify-center gap-3 px-12 py-5 text-white font-semibold w-full sm:w-auto text-lg"
        >
          进入测评平台
          <ArrowRight className="w-5 h-5" />
        </a>
      </div>
    </section>
  );
};

// --- Main Layout ---
export default function LandingPage() {
  return (
    <div className="simchip-landing min-h-screen bg-black text-zinc-300 font-sans selection:bg-cyan-500/30 selection:text-cyan-50 relative">
      <Navbar />
      <HeroSection />
      <ObjectivesSection />
      <CapabilitiesSection />
      <ArchitectureSection />
      <WorkflowSection />
      <FinalCTASection />
      
      <footer className="py-12 text-center text-zinc-500 text-sm font-mono relative z-10 border-t border-white/10 bg-black/40 backdrop-blur-xl">
        <p>© 2026 SimChip Nexus. All rights reserved.</p>
        <p className="mt-2 text-zinc-600">Built for Hardware-in-the-Loop Simulation & Research.</p>
      </footer>
    </div>
  );
}
