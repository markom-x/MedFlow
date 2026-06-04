"use client";

import { useId } from "react";
import { motion } from "framer-motion";

const easeOut = [0.22, 1, 0.36, 1] as const;

const rowReveal = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: easeOut },
  },
};

const columnEnter = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: easeOut },
  },
};

const connectorVariants = {
  hidden: { opacity: 0, scale: 0.9 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.5, ease: easeOut },
  },
};

const flowRoot = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.22,
      delayChildren: 0.06,
    },
  },
};

/** Third column: glass shell + inner rows staggered */
const cardBlock = {
  hidden: { opacity: 0, y: 28, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      duration: 0.48,
      ease: easeOut,
      staggerChildren: 0.14,
      delayChildren: 0.06,
    },
  },
};

const MESSAGGIO =
  "Doctor, I've had a really bad pain in my lower right tooth since last night, I took two ibuprofen but it won't go away — what should I do?";

function FlowConnector({
  className,
  gradV,
  gradH,
}: {
  className?: string;
  gradV: string;
  gradH: string;
}) {
  return (
    <motion.div className={className} variants={connectorVariants} aria-hidden>
      <div className="relative flex h-16 w-full items-center justify-center lg:hidden">
        <svg width="48" height="64" viewBox="0 0 48 64" className="overflow-visible" fill="none">
          <defs>
            <linearGradient id={gradV} x1="24" y1="0" x2="24" y2="64" gradientUnits="userSpaceOnUse">
              <stop stopColor="#8b5cf6" stopOpacity="0" />
              <stop offset="0.45" stopColor="#6366f1" stopOpacity="1" />
              <stop offset="1" stopColor="#3b82f6" stopOpacity="0" />
            </linearGradient>
          </defs>
          <motion.path
            d="M24 4 L24 52"
            stroke={`url(#${gradV})`}
            strokeWidth="3"
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: [0, 1], opacity: [0.45, 1, 0.45] }}
            transition={{
              pathLength: { duration: 1.35, ease: easeOut, repeat: Infinity, repeatDelay: 1.4 },
              opacity: { duration: 2.4, repeat: Infinity, ease: "easeInOut" },
            }}
          />
          <motion.path
            d="M14 46 L24 58 L34 46"
            stroke="#6366f1"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            animate={{ opacity: [0.65, 1, 0.65] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
          />
        </svg>
        <motion.div
          className="pointer-events-none absolute inset-x-1/4 top-1/2 h-8 -translate-y-1/2 rounded-full bg-violet-400/25 blur-xl"
          animate={{ scale: [1, 1.12, 1], opacity: [0.35, 0.55, 0.35] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="relative hidden h-24 w-full min-w-[5.5rem] max-w-[7rem] items-center justify-center lg:flex">
        <motion.div
          className="pointer-events-none absolute inset-y-1/2 left-0 right-0 h-6 -translate-y-1/2 rounded-full bg-gradient-to-r from-violet-500/0 via-violet-500/35 to-blue-500/0 blur-md"
          animate={{ opacity: [0.45, 0.9, 0.45], scaleX: [0.88, 1, 0.88] }}
          transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }}
        />
        <svg width="112" height="40" viewBox="0 0 112 40" className="overflow-visible" fill="none">
          <defs>
            <linearGradient id={gradH} x1="0" y1="20" x2="112" y2="20" gradientUnits="userSpaceOnUse">
              <stop stopColor="#8b5cf6" stopOpacity="0" />
              <stop offset="0.5" stopColor="#6366f1" stopOpacity="1" />
              <stop offset="1" stopColor="#3b82f6" stopOpacity="0" />
            </linearGradient>
          </defs>
          <motion.path
            d="M4 20 L92 20"
            stroke={`url(#${gradH})`}
            strokeWidth="3"
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: [0, 1] }}
            transition={{
              duration: 1.25,
              ease: easeOut,
              repeat: Infinity,
              repeatDelay: 1.65,
            }}
          />
          <motion.path
            d="M82 10 L100 20 L82 30"
            stroke="#4f46e5"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            animate={{ opacity: [0.72, 1, 0.72] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
          />
        </svg>
      </div>
    </motion.div>
  );
}

export function FlowPreview() {
  const uid = useId().replace(/:/g, "");
  const gradV = `flow-preview-v-${uid}`;
  const gradH = `flow-preview-h-${uid}`;

  return (
    <div className="mt-14 md:mt-20">
      <div className="relative mx-auto max-w-5xl rounded-3xl border border-white/60 bg-white/50 p-1 shadow-2xl shadow-slate-900/[0.08] backdrop-blur-md md:p-2">
        <div className="overflow-hidden rounded-[1.35rem] border border-slate-100/80 bg-gradient-to-br from-white via-slate-50/80 to-violet-50/30 p-6 md:p-10">
          <div className="mb-8 text-center md:mb-10 md:text-left">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Flow preview
            </p>
            <p className="mt-1 text-lg font-semibold text-slate-900 md:text-xl">
              Message → structured record
            </p>
          </div>

          <motion.div
            className="flex flex-col items-stretch gap-6 lg:flex-row lg:items-center lg:justify-between lg:gap-4"
            variants={flowRoot}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.22, margin: "0px 0px -48px 0px" }}
          >
            <motion.div
              className="mx-auto w-full max-w-[22rem] shrink-0 lg:mx-0"
              variants={columnEnter}
            >
              <motion.div
                className="rounded-2xl border border-emerald-600/15 bg-[#dcf8c6] p-4 shadow-2xl shadow-emerald-900/10 ring-1 ring-white/40"
                animate={{ y: [0, -10, 0] }}
                transition={{
                  repeat: Infinity,
                  duration: 4,
                  ease: "easeInOut",
                }}
              >
                <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-900/50">
                  WhatsApp
                </p>
                <p className="mt-2 text-left text-sm leading-relaxed text-slate-900">{MESSAGGIO}</p>
                <div className="mt-3 flex justify-end">
                  <span className="text-[10px] text-emerald-900/40">09:41</span>
                </div>
              </motion.div>
            </motion.div>

            <FlowConnector className="shrink-0 lg:w-[7rem]" gradV={gradV} gradH={gradH} />

            <motion.div
              className="mx-auto w-full max-w-md shrink-0 rounded-2xl border border-white/20 bg-white/55 p-5 shadow-2xl shadow-slate-900/[0.12] backdrop-blur-md ring-1 ring-slate-200/40 lg:mx-0 lg:max-w-[20rem]"
              variants={cardBlock}
            >
              <div className="mb-4 flex items-center justify-between gap-2 border-b border-slate-200/60 pb-3">
                <span className="text-xs font-bold tracking-tight text-slate-800">MedFlow</span>
                <span className="text-[10px] font-medium text-slate-400">Triage</span>
              </div>

              <motion.div variants={rowReveal} className="mb-4">
                <span className="inline-flex rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-violet-700">
                  Structured summary
                </span>
              </motion.div>

              <motion.div variants={rowReveal} className="space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Patient
                </p>
                <p className="text-sm font-medium text-slate-900">
                  Unknown <span className="text-slate-500">(+39 333…)</span>
                </p>
              </motion.div>

              <motion.div variants={rowReveal} className="mt-4 space-y-1 border-t border-slate-200/50 pt-4">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Symptoms
                </p>
                <p className="text-sm leading-snug text-slate-700">
                  Acute lower right molar pain
                </p>
              </motion.div>

              <motion.div variants={rowReveal} className="mt-4 space-y-1 border-t border-slate-200/50 pt-4">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Medications
                </p>
                <p className="text-sm text-slate-700">Ibuprofen x2</p>
              </motion.div>
            </motion.div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
