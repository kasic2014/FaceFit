import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { type GrowthData, type InterviewHistoryPage } from "@/api/analysis";
import { useAuth } from "@/auth/auth-context";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

export default function DashboardApiPage() {
  const { auth, request } = useAuth();
  const [history, setHistory] = useState<InterviewHistoryPage | null>(null);
  const [growth, setGrowth] = useState<GrowthData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void Promise.all([
        request<InterviewHistoryPage>(
          "/api/v1/members/me/interview-sessions?page=0&size=20",
          { signal: controller.signal },
        ),
        request<GrowthData>("/api/v1/members/me/growth?limit=5", {
          signal: controller.signal,
        }),
      ])
        .then(([nextHistory, nextGrowth]) => {
          if (!active) return;
          setHistory(nextHistory);
          setGrowth(nextGrowth);
        })
        .catch((reason: unknown) => {
          if (
            !active ||
            (reason instanceof DOMException && reason.name === "AbortError")
          )
            return;
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to load dashboard data.",
          );
        });
    }, 0);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [request]);

  return (
    <main className="min-h-screen bg-ivory-50 text-ink-900">
      <PageContainer size="wide" className="py-10">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm text-ink-500">
              {auth?.member?.name ?? "Member"}
            </p>
            <h1 className="mt-2 text-3xl font-bold">Interview history</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              to="/source-resources"
              className="rounded-lg border border-line-300 px-4 py-2 text-sm font-bold text-ink-700"
            >
              Source data
            </Link>
            <Link
              to="/account/data"
              className="rounded-lg border border-line-300 px-4 py-2 text-sm font-bold text-ink-700"
            >
              Data controls
            </Link>
          </div>
        </div>
        {error ? (
          <p
            role="alert"
            className="mt-5 rounded-xl border border-sunset-300 bg-sunset-100 p-4 text-sm text-sunset-800"
          >
            {error}
          </p>
        ) : null}
        <section className="mt-7 grid gap-4 lg:grid-cols-[1.2fr_2fr]">
          <article className="rounded-2xl border border-line-200 bg-white p-6">
            <h2 className="text-lg font-bold">Growth</h2>
            {growth ? (
              <>
                <p className="mt-4 text-sm text-ink-600">
                  {growth.dataSufficiency === "SUFFICIENT"
                    ? "Trend is available from completed reports."
                    : "Complete more interviews to establish a trend."}
                </p>
                <p className="mt-5 text-3xl font-bold text-moss-800">
                  {growth.points.at(-1)?.overallScore.toFixed(1) ?? "-"}
                </p>
                <p className="mt-1 text-sm text-ink-600">
                  Latest overall score
                </p>
                {growth.latestImprovement ? (
                  <div className="mt-5 rounded-xl bg-ivory-100 p-4">
                    <p className="font-bold text-moss-800">
                      {growth.latestImprovement.title}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-ink-600">
                      {growth.latestImprovement.practice}
                    </p>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="mt-4 text-sm text-ink-600">
                Loading growth data...
              </p>
            )}
          </article>
          <article className="rounded-2xl border border-line-200 bg-white p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Recent interviews</h2>
              <Link
                to="/onboarding"
                className="rounded-lg bg-moss-900 px-4 py-2 text-sm font-bold text-white"
              >
                New interview
              </Link>
            </div>
            {history ? (
              <div className="mt-5 space-y-3">
                {history.items.length === 0 ? (
                  <p className="text-sm text-ink-600">No interviews yet.</p>
                ) : (
                  history.items.map((item) => (
                    <Link
                      key={item.sessionId}
                      to={
                        item.reportId
                          ? `/records/${item.sessionId}`
                          : `/sessions/${item.sessionId}/analysis`
                      }
                      className="block rounded-xl bg-ivory-100 p-4 transition hover:bg-ivory-200"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="font-bold">{item.companyName}</p>
                          <p className="mt-1 text-sm text-ink-600">
                            {item.targetJobRole} - {item.persona} -{" "}
                            {item.sessionStatus}
                          </p>
                        </div>
                        <strong className="text-moss-800">
                          {item.overallScore === null
                            ? "In progress"
                            : item.overallScore.toFixed(1)}
                        </strong>
                      </div>
                    </Link>
                  ))
                )}
              </div>
            ) : (
              <p className="mt-5 text-sm text-ink-600">
                Loading interview history...
              </p>
            )}
          </article>
        </section>
      </PageContainer>
    </main>
  );
}
