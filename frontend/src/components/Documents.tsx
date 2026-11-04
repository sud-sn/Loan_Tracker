import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Eye, FileText, Lock, RotateCw, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api/client";
import type { DocumentOut } from "@/api/types";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage } from "@/i18n";
import { dmy } from "@/lib/format";

import { ConfirmSheet } from "./Confirm";
import { Button } from "./ui/button";
import { Field, Select } from "./ui/field";
import { EmptyState } from "./ui/states";

const BORROWER_TYPES = ["aadhaar", "pan", "photo", "address_proof", "other"];
const LOAN_TYPES = ["agreement", "promissory_note", "cheque", "photo", "other"];

interface Upload {
  id: string;
  file: File;
  progress: number;
  error?: string;
}

function csrf(): string {
  return decodeURIComponent(document.cookie.match(/(?:^|; )lt_csrf=([^;]+)/)?.[1] ?? "");
}

function send(file: File, ownerType: string, ownerId: string, docType: string, onProgress: (n: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const form = new FormData();
    form.append("owner_type", ownerType);
    form.append("owner_id", ownerId);
    form.append("doc_type", docType);
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/documents");
    xhr.setRequestHeader("X-CSRF-Token", csrf());
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      if (xhr.status < 300) return resolve();
      try {
        reject(new Error(JSON.parse(xhr.responseText).error.code));
      } catch {
        reject(new Error(`HTTP_${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error(navigator.onLine ? "NETWORK_ERROR" : "OFFLINE"));
    xhr.send(form);
  });
}

/** Several files at once, from the camera or the gallery, with progress and retry (PRD section 8). */
export function Documents({ ownerType, ownerId, maxMb = 10 }: { ownerType: "borrower" | "loan"; ownerId: string;
  maxMb?: number }) {
  const { t, i18n } = useTranslation();
  const { isOwner } = useAuth();
  const qc = useQueryClient();
  const types = ownerType === "borrower" ? BORROWER_TYPES : LOAN_TYPES;
  const [docType, setDocType] = useState(types[0]);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [toDelete, setToDelete] = useState<DocumentOut | null>(null);
  const galleryRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const key = ["documents", ownerType, ownerId];
  const docs = useQuery({ queryKey: key, queryFn: () => api.get<DocumentOut[]>("/documents", { owner_type: ownerType,
    owner_id: ownerId }) });
  const open = useMutation({
    mutationFn: ({ id, download }: { id: string; download: boolean }) =>
      api.post<{ url: string }>(`/documents/${id}/link`, undefined, { download }),
    onSuccess: ({ url }) => window.open(url, "_blank", "noopener"),
  });

  const start = (item: Upload) => {
    setUploads((u) => u.map((x) => (x.id === item.id ? { ...x, error: undefined, progress: 0 } : x)));
    send(item.file, ownerType, ownerId, docType, (p) =>
      setUploads((u) => u.map((x) => (x.id === item.id ? { ...x, progress: p } : x))))
      .then(() => {
        setUploads((u) => u.filter((x) => x.id !== item.id));
        void qc.invalidateQueries({ queryKey: key });
      })
      .catch((err: Error) => {
        const code = err.message;
        const msg = i18n.exists(`errors.${code}`) ? t(`errors.${code}`, { max_mb: maxMb }) : t("errors.unknown", { code });
        setUploads((u) => u.map((x) => (x.id === item.id ? { ...x, error: msg } : x)));
      });
  };
  const add = (files: FileList | null) => {
    const items = Array.from(files ?? []).map((file) => ({ id: crypto.randomUUID(), file, progress: 0 }));
    setUploads((u) => [...u, ...items]);
    items.forEach(start);
  };

  return (
    <section className="space-y-3" aria-labelledby={`docs-${ownerId}`}>
      <h3 id={`docs-${ownerId}`} className="text-lg">{t("doc.title")}</h3>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
        <Field label={t("doc.type")}>
          {(id) => (
            <Select id={id} value={docType} onChange={(e) => setDocType(e.target.value)}>
              {types.map((d) => <option key={d} value={d}>{t(`doc.types.${d}`)}</option>)}
            </Select>
          )}
        </Field>
        <Button variant="secondary" onClick={() => cameraRef.current?.click()}>
          <Camera className="h-5 w-5" aria-hidden />{t("doc.camera")}
        </Button>
        <Button variant="outline" onClick={() => galleryRef.current?.click()}>
          <Upload className="h-5 w-5" aria-hidden />{t("doc.upload")}
        </Button>
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden"
          onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
        <input ref={galleryRef} type="file" multiple accept="application/pdf,image/jpeg,image/png,image/heic,image/heif"
          className="hidden" onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      </div>
      <p className="text-sm text-muted">{t("doc.rules", { mb: maxMb })}</p>
      {uploads.map((u) => (
        <div key={u.id} className="rounded-xl border border-line p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate">{u.error ? t("doc.failed", { name: u.file.name }) : t("doc.uploading", { name: u.file.name })}</span>
            {u.error && <Button size="sm" variant="outline" onClick={() => start(u)}><RotateCw className="h-4 w-4" aria-hidden />{t("doc.retry")}</Button>}
          </div>
          {u.error ? <p role="alert" className="field-error">{u.error}</p> : (
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuenow={u.progress}
              aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full bg-brand transition-all" style={{ width: `${u.progress}%` }} />
            </div>
          )}
        </div>
      ))}
      {docs.data && docs.data.length === 0 && uploads.length === 0 && <EmptyState text={t("doc.empty")} />}
      <ul className="space-y-2">
        {docs.data?.map((d) => (
          <li key={d.id} className="flex items-center gap-3 rounded-xl border border-line p-3">
            <FileText className="h-6 w-6 shrink-0 text-brand" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{t(`doc.types.${d.doc_type}`)}</p>
              <p className="truncate text-sm text-muted">{d.original_name} · {dmy(String(d.created_at))}</p>
            </div>
            {d.can_view ? (
              <Button size="icon" variant="ghost" aria-label={t("app.view")} onClick={() => open.mutate({ id: d.id, download: false })}>
                <Eye className="h-5 w-5" aria-hidden />
              </Button>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm text-muted" title={t("doc.ownerOnly")}>
                <Lock className="h-4 w-4" aria-hidden /><span className="sr-only">{t("doc.ownerOnly")}</span>
              </span>
            )}
            {isOwner && d.can_delete && (
              <Button size="icon" variant="ghost" aria-label={t("app.delete")} onClick={() => setToDelete(d)}>
                <Trash2 className="h-5 w-5 text-late" aria-hidden />
              </Button>
            )}
          </li>
        ))}
      </ul>
      {open.error && <p role="alert" className="field-error">{errorMessage(open.error)}</p>}
      <ConfirmSheet open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title={t("app.delete")}
        body={t("doc.deleteConfirm")} confirmLabel={t("app.delete")} danger
        onConfirm={async () => {
          await api.delete(`/documents/${toDelete?.id}`);
          await qc.invalidateQueries({ queryKey: key });
        }} />
    </section>
  );
}
