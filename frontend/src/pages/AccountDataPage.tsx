import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { type LegalConsentPage, type LegalConsentRevocation, type MemberDeletion } from "@/api/privacy";
import { poll } from "@/api/polling";
import { useAuth } from "@/auth/auth-context";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

export default function AccountDataPage() {
  const { request, requestWithResponse } = useAuth();
  const [confirmed, setConfirmed] = useState(false);
  const [deletion, setDeletion] = useState<MemberDeletion | null>(null);
  const [deletionToken, setDeletionToken] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [consents, setConsents] = useState<LegalConsentPage | null>(null);
  const [revokingConsentId, setRevokingConsentId] = useState<string | null>(null);

  useEffect(() => {
    if (!deletionToken || deletion?.status === "COMPLETED" || deletion?.status === "FAILED") return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void poll<MemberDeletion>({
        load: () => requestWithResponse<MemberDeletion>("/api/v1/members/me/deletion", { headers: { "Deletion-Status-Token": deletionToken }, signal: controller.signal }).then((response) => response.data),
        onValue: setDeletion,
        shouldContinue: (value) => value.status === "QUEUED" || value.status === "PROCESSING",
        intervalMs: 5000,
        maxWaitMs: 10 * 60 * 1000,
        signal: controller.signal,
      }).catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to load deletion status.");
      });
    }, 0);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [deletion?.status, deletionToken, requestWithResponse]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void request<LegalConsentPage>("/api/v1/legal-consents?status=ACTIVE&page=0&size=100", { signal: controller.signal })
        .then((value) => { if (active) setConsents(value); })
        .catch((reason: unknown) => {
          if (!active || (reason instanceof DOMException && reason.name === "AbortError")) return;
          setError(reason instanceof Error ? reason.message : "Unable to load consent records.");
        });
    }, 0);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [request]);

  const requestDeletion = async () => {
    if (!confirmed || deletion) return;
    setError("");
    try {
      const response = await requestWithResponse<MemberDeletion>("/api/v1/members/me", { method: "DELETE", body: { confirmation: "DELETE_MY_ACCOUNT" } });
      const token = response.headers.get("Deletion-Status-Token");
      if (!token) throw new Error("Deletion status token was not returned.");
      setDeletion(response.data);
      setDeletionToken(token);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start account deletion.");
    }
  };

  const revokeConsent = async (consentRecordId: string) => {
    setRevokingConsentId(consentRecordId);
    setError("");
    try {
      await request<LegalConsentRevocation>(`/api/v1/legal-consents/${consentRecordId}`, { method: "DELETE" });
      setConsents((current) => current ? { ...current, items: current.items.filter((item) => item.consentRecordId !== consentRecordId), totalElements: Math.max(0, current.totalElements - 1) } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to revoke consent.");
    } finally {
      setRevokingConsentId(null);
    }
  };

  return <main className="min-h-screen bg-ivory-50 text-ink-900"><PageContainer size="narrow" className="py-14"><Link to="/dashboard" className="text-sm font-bold text-moss-800">Back to dashboard</Link><section className="mt-6 rounded-2xl border border-line-200 bg-white p-7"><p className="text-sm font-bold text-moss-700">Consent records</p><h1 className="mt-3 text-2xl font-bold">Manage feature consents</h1><p className="mt-3 text-sm leading-6 text-ink-600">Revoking a consent disables its dependent feature. Interview-media consent cannot be revoked after recording begins; remove original media instead.</p><div className="mt-6 space-y-3">{consents?.items.map((consent) => <div key={consent.consentRecordId} className="flex items-center justify-between gap-3 rounded-xl bg-ivory-100 p-4"><div><p className="font-bold text-ink-900">{consent.documentType}</p><p className="mt-1 text-xs text-ink-600">Version {consent.documentVersion}</p></div><button type="button" disabled={revokingConsentId === consent.consentRecordId} onClick={() => void revokeConsent(consent.consentRecordId)} className="rounded-lg border border-sunset-300 px-3 py-2 text-sm font-bold text-sunset-700 disabled:opacity-50">{revokingConsentId === consent.consentRecordId ? "Revoking" : "Revoke"}</button></div>) ?? <p className="text-sm text-ink-600">Loading active consent records...</p>}</div></section><section className="mt-6 rounded-2xl border border-sunset-300 bg-white p-7"><p className="text-sm font-bold text-sunset-700">Account deletion</p><h2 className="mt-3 text-2xl font-bold">Delete your account and stored data</h2><p className="mt-3 text-sm leading-6 text-ink-600">This starts deletion of your account, source files, media, voice profile, and derived data according to the retention policy.</p>{deletion ? <div className="mt-6 rounded-xl bg-ivory-100 p-4"><p className="font-bold text-ink-900">Status: {deletion.status}</p><p className="mt-2 text-sm text-ink-600">{deletion.status === "FAILED" ? `Failed targets: ${deletion.failedTargets.join(", ")}` : "The page checks the deletion status automatically."}</p></div> : <><label className="mt-6 flex gap-3 text-sm text-ink-700"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-0.5 size-4" />I understand that this cannot be undone.</label><button type="button" disabled={!confirmed} onClick={() => void requestDeletion()} className="mt-6 rounded-xl bg-sunset-600 px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-line-300">Delete account</button></>}{error ? <p role="alert" className="mt-5 text-sm text-sunset-700">{error}</p> : null}</section></PageContainer></main>;
}
