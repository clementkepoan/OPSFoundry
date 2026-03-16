import { Dashboard } from "../../../components/dashboard";

export default async function WorkflowPage({
  params,
}: {
  params: Promise<{ workflowName: string }>;
}) {
  const { workflowName } = await params;
  return <Dashboard workflowName={decodeURIComponent(workflowName)} />;
}
