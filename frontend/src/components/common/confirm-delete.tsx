type ConfirmDeleteProps = {
  title: string;
  description: string;
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  loading?: boolean;
};

export function ConfirmDelete({
  title,
  description,
  open,
  onCancel,
  onConfirm,
  loading = false,
}: ConfirmDeleteProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 backdrop-blur-sm">
      <div className="glass-panel w-full max-w-md rounded-2xl p-5">
        <h3 className="glass-title text-lg font-semibold">{title}</h3>
        <p className="glass-muted mt-2 text-sm">{description}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="glass-btn glass-focus cursor-pointer rounded-lg px-3 py-2 text-sm transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="glass-btn-danger glass-focus cursor-pointer rounded-lg px-3 py-2 text-sm transition disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
