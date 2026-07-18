import { RepositoryDetailClient } from "./repository-detail-client";

export default async function RepositoryDetailPage({
  params,
}: {
  params: Promise<{ repositoryId: string }>;
}) {
  const { repositoryId } = await params;
  return <RepositoryDetailClient repositoryId={repositoryId} />;
}
