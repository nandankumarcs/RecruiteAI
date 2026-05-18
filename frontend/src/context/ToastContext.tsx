import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
  duration?: number;
}

interface ToastContextValue {
  toast: (input: Omit<ToastItem, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

// ─── Individual Toast ────────────────────────────────────────────────────────

function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    // Trigger enter animation on next frame
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  const dismiss = useCallback(() => {
    setLeaving(true);
    window.setTimeout(onDismiss, 300);
  }, [onDismiss]);

  const config = {
    success: {
      icon: <CheckCircle2 className="h-[18px] w-[18px]" />,
      bar: "bg-emerald-400",
      iconColor: "text-emerald-400",
    },
    error: {
      icon: <AlertCircle className="h-[18px] w-[18px]" />,
      bar: "bg-rose-400",
      iconColor: "text-rose-400",
    },
    info: {
      icon: <Info className="h-[18px] w-[18px]" />,
      bar: "bg-blue-400",
      iconColor: "text-blue-400",
    },
  }[item.variant];

  return (
    <div
      style={{
        transition: "opacity 280ms ease, transform 280ms cubic-bezier(0.34,1.56,0.64,1)",
        opacity: visible && !leaving ? 1 : 0,
        transform: visible && !leaving ? "translateY(0) scale(1)" : "translateY(12px) scale(0.97)",
      }}
      className="pointer-events-auto w-full overflow-hidden rounded-xl border border-white/10 bg-zinc-900 shadow-2xl shadow-black/40"
    >
      {/* Coloured left accent bar */}
      <div className={`absolute inset-y-0 left-0 w-[3px] ${config.bar}`} />

      <div className="flex items-start gap-3 px-4 py-3.5 pl-5">
        {/* Icon */}
        <span className={`mt-0.5 shrink-0 ${config.iconColor}`}>{config.icon}</span>

        {/* Text */}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-snug text-white">{item.title}</p>
          {item.description && (
            <p className="mt-0.5 text-[13px] leading-snug text-zinc-400">{item.description}</p>
          )}
        </div>

        {/* Dismiss */}
        <button
          type="button"
          onClick={dismiss}
          className="ml-1 mt-0.5 shrink-0 rounded-md p-1 text-zinc-500 transition hover:bg-white/10 hover:text-zinc-300"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Auto-dismiss progress bar */}
      <div className="relative h-[2px] w-full bg-white/5">
        <div
          className={`absolute inset-y-0 left-0 ${config.bar} opacity-40`}
          style={{
            animation: `toast-shrink ${item.duration ?? 4000}ms linear forwards`,
          }}
        />
      </div>
    </div>
  );
}

// ─── Provider ────────────────────────────────────────────────────────────────

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    ({ title, description, variant = "info", duration = 4000 }: Omit<ToastItem, "id">) => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      setToasts((current) => [...current, { id, title, description, variant, duration }]);
      window.setTimeout(() => dismiss(id), duration + 300 /* leave animation buffer */);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}

      {/* Keyframe for shrinking progress bar */}
      <style>{`
        @keyframes toast-shrink {
          from { width: 100%; }
          to   { width: 0%; }
        }
      `}</style>

      <div className="pointer-events-none fixed bottom-5 right-5 z-[9999] flex w-[360px] flex-col gap-2.5">
        {toasts.map((item) => (
          <div key={item.id} className="relative">
            <Toast item={item} onDismiss={() => dismiss(item.id)} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within a ToastProvider");
  return context;
}
