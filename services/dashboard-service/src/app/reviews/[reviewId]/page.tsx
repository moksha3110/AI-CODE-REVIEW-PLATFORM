import { ReviewDetailClient } from "./review-detail-client";

export default async function ReviewDetailPage({
  params,
}: {
  params: Promise<{ reviewId: string }>;
}) {
  const { reviewId } = await params;
  return <ReviewDetailClient reviewId={reviewId} />;
}
