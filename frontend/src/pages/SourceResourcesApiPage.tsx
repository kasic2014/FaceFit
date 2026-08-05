import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { useAuth } from "@/auth/auth-context";
import type {
  CareerDocumentPage,
  JobPosting,
  JobPostingPage,
  JobPostingUpdate,
  ResumeInterviewProfileSummary,
} from "@/api/setup";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

type LoadState = "loading" | "ready" | "error";

const splitLines = (value: string) =>
  value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

function updateForm(job: JobPosting): JobPostingUpdate {
  return {
    ...(job.companyName ? { companyName: job.companyName } : {}),
    ...(job.targetJobRole ? { targetJobRole: job.targetJobRole } : {}),
    ...(job.mainResponsibilities
      ? { mainResponsibilities: job.mainResponsibilities }
      : {}),
    ...(job.qualifications ? { qualifications: job.qualifications } : {}),
    ...(job.preferredQualifications
      ? { preferredQualifications: job.preferredQualifications }
      : {}),
    ...(job.technologiesTools
      ? { technologiesTools: job.technologiesTools }
      : {}),
    ...(job.coreCompetencies ? { coreCompetencies: job.coreCompetencies } : {}),
    ...(job.companyBusinessIntro
      ? { companyBusinessIntro: job.companyBusinessIntro }
      : {}),
  };
}

export default function SourceResourcesApiPage() {
  const { request } = useAuth();
  const [state, setState] = useState<LoadState>("loading");
  const [documents, setDocuments] = useState<CareerDocumentPage["items"]>([]);
  const [jobs, setJobs] = useState<JobPostingPage["items"]>([]);
  const [message, setMessage] = useState("");
  const [profile, setProfile] = useState<ResumeInterviewProfileSummary | null>(
    null,
  );
  const [editingJob, setEditingJob] = useState<JobPosting | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setState("loading");
    try {
      const [documentPage, jobPage] = await Promise.all([
        request<CareerDocumentPage>("/api/v1/career-documents?page=0&size=50"),
        request<JobPostingPage>("/api/v1/job-postings?page=0&size=50"),
      ]);
      setDocuments(documentPage.items);
      setJobs(jobPage.items);
      setState("ready");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to load source resources.",
      );
      setState("error");
    }
  }, [request]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const deleteResource = async (path: string) => {
    if (
      !window.confirm(
        "Delete this source resource? Active interview sessions may prevent deletion.",
      )
    )
      return;
    try {
      await request<void>(path, { method: "DELETE" });
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to delete the resource.",
      );
    }
  };

  const openProfile = async (documentId: string) => {
    try {
      setProfile(
        await request<ResumeInterviewProfileSummary>(
          `/api/v1/career-documents/${documentId}/analysis`,
        ),
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to load the document analysis.",
      );
    }
  };

  const saveJob = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingJob) return;
    const form = new FormData(event.currentTarget);
    const mainResponsibilities = splitLines(
      String(form.get("mainResponsibilities") ?? ""),
    );
    const qualifications = splitLines(String(form.get("qualifications") ?? ""));
    const payload: JobPostingUpdate = {
      companyName: String(form.get("companyName") ?? "").trim(),
      targetJobRole: String(
        form.get("targetJobRole"),
      ) as JobPostingUpdate["targetJobRole"],
      mainResponsibilities,
      qualifications,
      preferredQualifications: splitLines(
        String(form.get("preferredQualifications") ?? ""),
      ),
      technologiesTools: splitLines(
        String(form.get("technologiesTools") ?? ""),
      ),
      coreCompetencies: splitLines(String(form.get("coreCompetencies") ?? "")),
      companyBusinessIntro: String(
        form.get("companyBusinessIntro") ?? "",
      ).trim(),
    };
    if (
      !payload.companyName ||
      !payload.targetJobRole ||
      !mainResponsibilities.length ||
      !qualifications.length
    ) {
      setMessage(
        "Company, job role, responsibilities, and qualifications are required.",
      );
      return;
    }
    setSaving(true);
    try {
      await request<JobPosting>(
        `/api/v1/job-postings/${editingJob.jobPostingId}`,
        { method: "PATCH", body: payload },
      );
      setEditingJob(null);
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to update the job posting.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="min-h-screen bg-ivory-50 text-ink-900">
      <PageContainer size="wide" className="py-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-moss-700">SOURCE DATA</p>
            <h1 className="mt-2 text-3xl font-bold tracking-[-.04em]">
              Documents and job postings
            </h1>
            <p className="mt-3 text-sm leading-6 text-ink-600">
              Manage only your uploaded inputs. A resource in an active
              interview cannot be deleted.
            </p>
          </div>
          <Link
            to="/onboarding"
            className="rounded-lg bg-moss-900 px-4 py-2 text-sm font-bold text-white"
          >
            New interview
          </Link>
        </div>
        {message ? (
          <p
            role="alert"
            className="mt-5 rounded-xl border border-sunset-300 bg-white p-4 text-sm text-sunset-800"
          >
            {message}
          </p>
        ) : null}
        {state === "loading" ? (
          <p role="status" className="mt-8 text-sm text-ink-600">
            Loading source resources...
          </p>
        ) : null}
        {state === "error" ? (
          <button
            type="button"
            onClick={() => void load()}
            className="mt-5 rounded-lg border border-line-300 px-4 py-2 text-sm font-bold"
          >
            Try again
          </button>
        ) : null}
        {state === "ready" ? (
          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <section className="rounded-2xl border border-line-200 bg-white p-6">
              <h2 className="text-lg font-bold">Career documents</h2>
              <div className="mt-4 space-y-3">
                {documents.length === 0 ? (
                  <p className="text-sm text-ink-600">
                    No documents uploaded yet.
                  </p>
                ) : (
                  documents.map((document) => (
                    <article
                      key={document.documentId}
                      className="rounded-xl bg-ivory-100 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-bold">
                            {document.originalFileName}
                          </p>
                          <p className="mt-1 text-xs text-ink-600">
                            {document.documentType} · {document.status}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            void deleteResource(
                              `/api/v1/career-documents/${document.documentId}`,
                            )
                          }
                          className="text-xs font-bold text-sunset-700"
                        >
                          Delete
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() => void openProfile(document.documentId)}
                        className="mt-3 text-sm font-bold text-moss-800 underline underline-offset-4"
                      >
                        View interview profile
                      </button>
                    </article>
                  ))
                )}
              </div>
            </section>
            <section className="rounded-2xl border border-line-200 bg-white p-6">
              <h2 className="text-lg font-bold">Job postings</h2>
              <div className="mt-4 space-y-3">
                {jobs.length === 0 ? (
                  <p className="text-sm text-ink-600">
                    No job postings uploaded yet.
                  </p>
                ) : (
                  jobs.map((job) => (
                    <article
                      key={job.jobPostingId}
                      className="rounded-xl bg-ivory-100 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-bold">
                            {job.companyName ??
                              job.originalFileName ??
                              "Job posting"}
                          </p>
                          <p className="mt-1 text-xs text-ink-600">
                            {job.targetJobRole ?? "Role not confirmed"} ·{" "}
                            {job.processingStatus}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            void deleteResource(
                              `/api/v1/job-postings/${job.jobPostingId}`,
                            )
                          }
                          className="text-xs font-bold text-sunset-700"
                        >
                          Delete
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() => setEditingJob(job)}
                        className="mt-3 text-sm font-bold text-moss-800 underline underline-offset-4"
                      >
                        Review extracted fields
                      </button>
                    </article>
                  ))
                )}
              </div>
            </section>
          </div>
        ) : null}
        {profile ? (
          <section className="mt-6 rounded-2xl border border-line-200 bg-white p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold">Interview profile</h2>
                <p className="mt-2 text-sm text-ink-600">
                  {profile.status} · experiences {profile.experienceCount} ·
                  projects {profile.projectCount}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setProfile(null)}
                className="text-sm font-bold"
              >
                Close
              </button>
            </div>
            <p className="mt-4 text-sm font-semibold">
              Skills:{" "}
              {profile.skills
                .map((skill) => `${skill.name} (${skill.evidenceRefCount})`)
                .join(", ") || "Not available"}
            </p>
            {profile.missingInformation.length ? (
              <p className="mt-2 text-sm text-ink-600">
                Missing information: {profile.missingInformation.join(", ")}
              </p>
            ) : null}
            {profile.qualityFlags.length ? (
              <p className="mt-2 text-sm text-sunset-700">
                Quality flags: {profile.qualityFlags.join(", ")}
              </p>
            ) : null}
          </section>
        ) : null}
        {editingJob ? (
          <JobEditor
            job={editingJob}
            saving={saving}
            onCancel={() => setEditingJob(null)}
            onSubmit={saveJob}
          />
        ) : null}
      </PageContainer>
    </main>
  );
}

function JobEditor({
  job,
  saving,
  onCancel,
  onSubmit,
}: {
  job: JobPosting;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
}) {
  const initial = updateForm(job);
  const fields: Array<{
    name: keyof JobPostingUpdate;
    label: string;
    required?: boolean;
    multiline?: boolean;
  }> = [
    { name: "companyName", label: "Company", required: true },
    {
      name: "mainResponsibilities",
      label: "Responsibilities (one per line)",
      required: true,
      multiline: true,
    },
    {
      name: "qualifications",
      label: "Qualifications (one per line)",
      required: true,
      multiline: true,
    },
    {
      name: "preferredQualifications",
      label: "Preferred qualifications",
      multiline: true,
    },
    {
      name: "technologiesTools",
      label: "Technologies and tools",
      multiline: true,
    },
    { name: "coreCompetencies", label: "Core competencies", multiline: true },
    {
      name: "companyBusinessIntro",
      label: "Company introduction",
      multiline: true,
    },
  ];
  const value = (name: keyof JobPostingUpdate) => {
    const field = initial[name];
    return Array.isArray(field) ? field.join("\n") : (field ?? "");
  };
  return (
    <section className="mt-6 rounded-2xl border border-line-200 bg-white p-6">
      <h2 className="text-lg font-bold">Review job posting</h2>
      <form onSubmit={onSubmit} className="mt-5 grid gap-4">
        <label className="text-sm font-bold">
          Job role
          <select
            name="targetJobRole"
            defaultValue={initial.targetJobRole}
            className="mt-2 w-full rounded-lg border border-line-300 bg-white p-3 text-sm"
          >
            <option value="AI_ENGINEER">AI Engineer</option>
            <option value="ML_ENGINEER">ML Engineer</option>
            <option value="DATA_SCIENTIST">Data Scientist</option>
            <option value="DATA_ENGINEER">Data Engineer</option>
            <option value="MLOPS_ENGINEER">MLOps Engineer</option>
            <option value="LLM_ENGINEER">LLM Engineer</option>
            <option value="NLP_ENGINEER">NLP Engineer</option>
            <option value="COMPUTER_VISION_ENGINEER">
              Computer Vision Engineer
            </option>
            <option value="AI_PRODUCT_MANAGER">AI Product Manager</option>
          </select>
        </label>
        {fields.map((field) => (
          <label key={field.name} className="text-sm font-bold">
            {field.label}
            {field.multiline ? (
              <textarea
                name={field.name}
                defaultValue={value(field.name)}
                rows={3}
                className="mt-2 w-full rounded-lg border border-line-300 p-3 text-sm font-normal"
              />
            ) : (
              <input
                name={field.name}
                defaultValue={value(field.name)}
                required={field.required}
                className="mt-2 w-full rounded-lg border border-line-300 p-3 text-sm font-normal"
              />
            )}
          </label>
        ))}
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-moss-900 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save confirmed fields"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-line-300 px-4 py-2 text-sm font-bold"
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}
