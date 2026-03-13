import type { ReactNode } from "react";

type EntityModalProps = {
  title: string;
  open: boolean;
  onClose: () => void;
  actions?: ReactNode;
  children: ReactNode;
};

export function EntityModal({ title, open, onClose, actions, children }: EntityModalProps) {
  if (!open) return null;

  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center px-4 backdrop-blur-sm">
      <div className="glass-panel w-full max-w-4xl rounded-2xl p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="glass-title text-lg font-semibold">{title}</h3>
          <div className="flex items-center gap-2">
            {actions}
            <button
              type="button"
              onClick={onClose}
              className="glass-btn glass-focus cursor-pointer rounded-lg px-3 py-1.5 text-sm transition"
            >
              Close
            </button>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}
