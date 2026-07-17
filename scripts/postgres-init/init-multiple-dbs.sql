-- Each microservice owns its own logical database on the shared Postgres
-- instance (see architecture notes: database-per-service in ownership,
-- shared instance for cost reasons at this project's scale).
CREATE DATABASE auth_service;
CREATE DATABASE repository_service;
CREATE DATABASE ai_analysis_service;
CREATE DATABASE review_service;
