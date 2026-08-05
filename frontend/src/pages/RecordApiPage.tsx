import { Navigate, useParams } from "react-router";

export default function RecordApiPage() {
  const { sessionId } = useParams();
  return <Navigate to={sessionId ? `/sessions/${sessionId}/report` : "/dashboard"} replace />;
}
