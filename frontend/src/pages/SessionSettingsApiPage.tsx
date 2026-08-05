import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import type {
  CareerDocumentPage,
  Difficulty,
  InterviewSession,
  InterviewSessionUpdate,
  JobPostingPage,
  Persona,
} from "@/api/setup";
import { useAuth } from "@/auth/auth-context";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

type LoadState = "loading" | "ready" | "error";

export default function SessionSettingsApiPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { request } = useAuth();
  const [state, setState] = useState<LoadState>("loading");
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [documents, setDocuments] = useState<CareerDocumentPage["items"]>([]);
  const [jobs, setJobs] = useState<JobPostingPage["items"]>([]);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void Promise.all([
        request<InterviewSession>(`/api/v1/interview-sessions/${sessionId}`, {
          signal: controller.signal,
        }),
        request<CareerDocumentPage>(
          "/api/v1/career-documents?status=READY&page=0&size=50",
          { signal: controller.signal },
        ),
        request<JobPostingPage>(
          "/api/v1/job-postings?processingStatus=READY&page=0&size=50",
          { signal: controller.signal },
        ),
      ])
        .then(([nextSession, documentPage, jobPage]) => {
          if (!active) return;
          setSession(nextSession);
          setDocuments(documentPage.items);
          setJobs(jobPage.items);
          setState("ready");
        })
        .catch((error: unknown) => {
          if (
            !active ||
            (error instanceof DOMException && error.name === "AbortError")
          )
            return;
          setMessage(
            error instanceof Error
              ? error.message
              : "Unable to load session settings.",
          );
          setState("error");
        });
    }, 0);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [request, sessionId]);

  if (!sessionId) return <Navigate to="/onboarding" replace />;
  if (state === "loading")
    return (
      <main className="grid min-h-screen place-items-center bg-ivory-50 text-sm text-ink-600">
        Loading session settings...
      </main>
    );
  if (state === "error" || !session)
    return (
      <main className="grid min-h-screen place-items-center bg-ivory-50 p-5 text-center text-sm text-sunset-700">
        {message}
      </main>
    );
  if (session.status !== "DRAFT")
    return (
      <main className="grid min-h-screen place-items-center bg-ivory-50 p-5 text-center">
        <div>
          <p className="text-sm text-ink-700">
            Only draft sessions can be edited.
          </p>
          <Link
            to={`/equipment/${sessionId}`}
            className="mt-4 inline-block text-sm font-bold text-moss-800 underline underline-offset-4"
          >
            Back to equipment check
          </Link>
        </div>
      </main>
    );

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const coverLetterDocumentId = String(
      form.get("coverLetterDocumentId") ?? "",
    );
    const payload: InterviewSessionUpdate = {
      resumeDocumentId: String(form.get("resumeDocumentId")),
      coverLetterDocumentId: coverLetterDocumentId || null,
      jobPostingId: String(form.get("jobPostingId")),
      persona: String(form.get("persona")) as Persona,
      difficulty: String(form.get("difficulty")) as Difficulty,
    };
    if (!payload.resumeDocumentId || !payload.jobPostingId) {
      setMessage("A ready resume and job posting are required.");
      return;
    }
    setSaving(true);
    try {
      await request<InterviewSession>(
        `/api/v1/interview-sessions/${sessionId}`,
        { method: "PATCH", body: payload },
      );
      navigate(`/equipment/${sessionId}`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to save the session settings.",
      );
    } finally {
      setSaving(false);
    }
  };

  const resumeDocuments = documents.filter(
    (document) => document.documentType === "RESUME",
  );
  const coverLetters = documents.filter(
    (document) => document.documentType === "COVER_LETTER",
  );
  return (
    <main className="min-h-screen bg-ivory-50 text-ink-900">
      <PageContainer size="compact" className="py-10">
        <Link
          to={`/equipment/${sessionId}`}
          className="text-sm font-bold text-moss-800 underline underline-offset-4"
        >
          Back to equipment check
        </Link>
        <h1 className="mt-5 text-3xl font-bold tracking-[-.04em]">
          Review interview setup
        </h1>
        <p className="mt-3 text-sm leading-6 text-ink-600">
          Changes are applied only while this session is still a draft.
        </p>
        {message ? (
          <p
            role="alert"
            className="mt-5 rounded-xl border border-sunset-300 bg-white p-4 text-sm text-sunset-800"
          >
            {message}
          </p>
        ) : null}
        <form
          onSubmit={save}
          className="mt-8 space-y-5 rounded-2xl border border-line-200 bg-white p-6"
        >
          <ResourceSelect
            name="resumeDocumentId"
            label="Resume"
            items={resumeDocuments}
            value={session.resumeDocumentId}
            required
          />
          <ResourceSelect
            name="coverLetterDocumentId"
            label="Cover letter (optional)"
            items={coverLetters}
            value={session.coverLetterDocumentId ?? ""}
          />
          <label className="block text-sm font-bold">
            Job posting
            <select
              name="jobPostingId"
              defaultValue={session.jobPostingId}
              className="mt-2 w-full rounded-lg border border-line-300 bg-white p-3 text-sm font-normal"
            >
              {jobs.map((job) => (
                <option key={job.jobPostingId} value={job.jobPostingId}>
                  {job.companyName ?? job.originalFileName ?? job.jobPostingId}{" "}
                  · {job.targetJobRole ?? "Unconfirmed"}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-bold">
            Interviewer
            <select
              name="persona"
              defaultValue={session.persona}
              className="mt-2 w-full rounded-lg border border-line-300 bg-white p-3 text-sm font-normal"
            >
              <option value="TECHNICAL">Technical</option>
              <option value="HR">HR</option>
              <option value="EXECUTIVE">Executive</option>
            </select>
          </label>
          <label className="block text-sm font-bold">
            Difficulty
            <select
              name="difficulty"
              defaultValue={session.difficulty}
              className="mt-2 w-full rounded-lg border border-line-300 bg-white p-3 text-sm font-normal"
            >
              <option value="GENERAL">General</option>
              <option value="PRESSURE">Pressure</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={
              saving || resumeDocuments.length === 0 || jobs.length === 0
            }
            className="w-full rounded-lg bg-moss-900 px-4 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save settings"}
          </button>
        </form>
      </PageContainer>
    </main>
  );
}

function ResourceSelect({
  name,
  label,
  items,
  value,
  required = false,
}: {
  name: string;
  label: string;
  items: CareerDocumentPage["items"];
  value: string;
  required?: boolean;
}) {
  return (
    <label className="block text-sm font-bold">
      {label}
      <select
        name={name}
        defaultValue={value}
        required={required}
        className="mt-2 w-full rounded-lg border border-line-300 bg-white p-3 text-sm font-normal"
      >
        <option value="">
          {required ? "Select a ready document" : "Do not use a cover letter"}
        </option>
        {items.map((document) => (
          <option key={document.documentId} value={document.documentId}>
            {document.originalFileName}
          </option>
        ))}
      </select>
    </label>
  );
}
