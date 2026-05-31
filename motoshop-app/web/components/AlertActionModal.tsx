"use client";

import { useState, useCallback } from "react";
import { submitAlertAction, type SubmitActionBody } from "@/lib/api/alertActions";
import { enqueueAction } from "@/lib/offline/queue";

type Tab = "ordered" | "dismissed" | "postponed";

const TAB_LABELS: Record<Tab, string> = {
  ordered: "Pedir",
  dismissed: "Descartar",
  postponed: "Posponer",
};

interface FormData {
  quantity: string;
  supplier: string;
  reason: string;
  postponed_to: string;
  notes: string;
}

interface Props {
  sku: string;
  nomProducto: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function AlertActionModal({ sku, nomProducto, onClose, onSuccess }: Props): JSX.Element {
  const [tab, setTab] = useState<Tab>("ordered");
  const [form, setForm] = useState<FormData>({
    quantity: "",
    supplier: "",
    reason: "",
    postponed_to: "",
    notes: "",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof FormData, string>>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<"idle" | "success" | "error">("idle");
  const [offline] = useState(() => typeof navigator !== "undefined" && !navigator.onLine);

  const update = useCallback(
    (field: keyof FormData, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      setErrors((prev) => ({ ...prev, [field]: undefined }));
    },
    [],
  );

  function validate(): boolean {
    const next: Partial<Record<keyof FormData, string>> = {};
    if (tab === "ordered") {
      const q = Number(form.quantity);
      if (!form.quantity.trim()) next.quantity = "Requerido";
      else if (!Number.isFinite(q) || q <= 0) next.quantity = "Debe ser un número positivo";
    }
    if (tab === "dismissed" && !form.reason.trim()) {
      next.reason = "Indicá por qué descartás esta alerta";
    }
    if (tab === "postponed" && !form.postponed_to.trim()) {
      next.postponed_to = "Seleccioná una fecha";
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setSubmitting(true);
    setResult("idle");

    const body: SubmitActionBody = {
      action_type: tab,
      ...(tab === "ordered" && {
        quantity: Number(form.quantity),
        ...(form.supplier.trim() && { supplier: form.supplier.trim() }),
      }),
      ...(tab === "dismissed" && { reason: form.reason.trim() }),
      ...(tab === "postponed" && { postponed_to: form.postponed_to }),
      ...(form.notes.trim() && { notes: form.notes.trim() }),
    };

    try {
      const idempotencyKey = crypto.randomUUID();
      await submitAlertAction(sku, body, idempotencyKey);
      setResult("success");
      setTimeout(onSuccess, 1500);
    } catch {
      // Encolar offline para reintentar con backoff exponencial
      const fallbackKey = crypto.randomUUID();
      enqueueAction(sku, body, fallbackKey);
      setResult("error");
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
      <div className="w-full max-w-lg rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-secondary-dark">Gestionar alerta</h2>
            <p className="truncate text-xs text-gray-400">{sku} — {nomProducto}</p>
          </div>
          <button
            onClick={onClose}
            className="ml-2 rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Offline indicator */}
        {offline && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
            Sin conexión — la acción se guardará localmente
          </div>
        )}

        {/* Tabs */}
        <div className="mt-4 flex gap-2" role="tablist">
          {(["ordered", "dismissed", "postponed"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              data-active={tab === t}
              onClick={() => setTab(t)}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                tab === t
                  ? t === "ordered"
                    ? "bg-green-600 text-white"
                    : t === "dismissed"
                      ? "bg-gray-600 text-white"
                      : "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>

        {/* Form */}
        <div className="mt-4 space-y-3" role="tabpanel">
          {tab === "ordered" && (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">
                  Cantidad a pedir <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={form.quantity}
                  onChange={(e) => update("quantity", e.target.value)}
                  className={`${inputClass} ${errors.quantity ? "border-red-400" : ""}`}
                  placeholder="Ej: 50"
                />
                {errors.quantity && <p className="mt-1 text-xs text-red-500">{errors.quantity}</p>}
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Proveedor</label>
                <input
                  type="text"
                  value={form.supplier}
                  onChange={(e) => update("supplier", e.target.value)}
                  className={inputClass}
                  placeholder="Ej: ATMOPEL"
                />
              </div>
            </>
          )}

          {tab === "dismissed" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Motivo <span className="text-red-500">*</span>
              </label>
              <textarea
                value={form.reason}
                onChange={(e) => update("reason", e.target.value)}
                rows={3}
                className={`${inputClass} resize-none ${errors.reason ? "border-red-400" : ""}`}
                placeholder="Ej: Ya hay pedido en tránsito"
              />
              {errors.reason && <p className="mt-1 text-xs text-red-500">{errors.reason}</p>}
            </div>
          )}

          {tab === "postponed" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">
              Fecha de revisión <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={form.postponed_to}
                onChange={(e) => update("postponed_to", e.target.value)}
                className={`${inputClass} ${errors.postponed_to ? "border-red-400" : ""}`}
              />
              {errors.postponed_to && <p className="mt-1 text-xs text-red-500">{errors.postponed_to}</p>}
            </div>
          )}

          {/* Notes (compartido) */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">Notas (opcional)</label>
            <textarea
              value={form.notes}
              onChange={(e) => update("notes", e.target.value)}
              rows={2}
              className={`${inputClass} resize-none`}
              placeholder="Comentario adicional"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="mt-5 flex gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-medium text-white transition-colors disabled:opacity-50 ${
              tab === "ordered"
                ? "bg-green-600 hover:bg-green-700"
                : tab === "dismissed"
                  ? "bg-gray-600 hover:bg-gray-700"
                  : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            {submitting ? "Guardando..." : result === "success" ? "✓ Guardado" : TAB_LABELS[tab]}
          </button>
        </div>

        {/* Error feedback */}
        {result === "error" && (
          <p className="mt-3 text-center text-xs text-amber-600">
            Error de conexión — la acción quedó en cola para reintentar automáticamente.
          </p>
        )}
      </div>
    </div>
  );
}
