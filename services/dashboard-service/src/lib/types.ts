// Mirrors the Pydantic response schemas each backend service actually
// returns - kept in one file so a backend schema change is a one-file diff
// here, not a hunt through every component that touches that shape.

// --- auth-service ---

export interface User {
  id: string;
  github_login: string;
  email: string | null;
  avatar_url: string | null;
  created_at: string;
}

// --- repository-service ---

export interface Repository {
  id: string;
  full_name: string;
  default_branch: string;
  is_private: boolean;
  updated_at: string;
}

export interface InstallUrlOut {
  install_url: string;
}

// --- review-service ---

export type IssueSeverity = "low" | "medium" | "high" | "critical";

export interface Issue {
  description: string;
  severity: IssueSeverity;
  line: number | null;
}

export interface Optimization {
  description: string;
  line: number | null;
}

export interface FileReview {
  file_path: string;
  summary: string;
  complexity_score: number;
  bug_count: number;
  security_issue_count: number;
  optimization_count: number;
  bugs: Issue[];
  security_issues: Issue[];
  optimizations: Optimization[];
  documentation_suggestions: string[];
}

export interface ReviewSummary {
  id: string;
  repository_id: string;
  repository_full_name: string;
  ref: string;
  after_sha: string;
  overall_complexity_score: number;
  total_bug_count: number;
  total_security_issue_count: number;
  analyzed_at: string;
}

export interface ReviewDetail extends ReviewSummary {
  file_reviews: FileReview[];
}

export interface PaginatedReviews {
  items: ReviewSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface QualityTrendPoint {
  analyzed_at: string;
  overall_complexity_score: number;
  total_bug_count: number;
  total_security_issue_count: number;
}

// --- notification-service ---

export interface Notification {
  id: string;
  repository_id: string;
  repository_full_name: string;
  after_sha: string;
  overall_complexity_score: number;
  total_bug_count: number;
  total_security_issue_count: number;
  message: string;
  read_at: string | null;
  created_at: string;
}

export interface PaginatedNotifications {
  items: Notification[];
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
}

// --- shared error envelope every service returns ---

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}
