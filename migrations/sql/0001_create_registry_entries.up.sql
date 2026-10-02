CREATE TABLE registry_entries (
    id INTEGER PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    version VARCHAR(32) NOT NULL DEFAULT '1',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    tools JSON,
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_registry_entries_name
    ON registry_entries (name);

CREATE INDEX ix_registry_entries_is_active
    ON registry_entries (is_active);
