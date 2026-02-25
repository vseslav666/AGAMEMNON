type AlertProps = {
  message: string;
  variant?: "error" | "success" | "info";
};

const styles: Record<NonNullable<AlertProps["variant"]>, string> = {
  error:
    "status-chip-error backdrop-blur-xl shadow-[0_8px_30px_rgba(239,68,68,0.18)]",
  success:
    "status-chip-success backdrop-blur-xl shadow-[0_8px_30px_rgba(16,185,129,0.18)]",
  info:
    "status-chip-info backdrop-blur-xl shadow-[0_8px_30px_rgba(14,165,233,0.18)]",
};

export function Alert({ message, variant = "error" }: AlertProps) {
  return (
    <div
      className={`rounded-xl border px-3 py-2 text-sm ${styles[variant]}`}
      role="alert"
      aria-live="polite"
    >
      {message}
    </div>
  );
}
