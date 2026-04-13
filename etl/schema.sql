-- Core tables populated by ETL
CREATE TABLE IF NOT EXISTS works (
    work_id          VARCHAR PRIMARY KEY,
    title            VARCHAR,
    publication_year INTEGER,
    cited_by_count   INTEGER,
    abstract_text    VARCHAR,
    primary_topic_id VARCHAR
);

CREATE TABLE IF NOT EXISTS work_topics (
    work_id     VARCHAR,
    topic_id    VARCHAR,
    topic_name  VARCHAR,
    score       DOUBLE,
    subfield_id VARCHAR
);

CREATE TABLE IF NOT EXISTS authorships (
    work_id          VARCHAR,
    author_id        VARCHAR,
    author_name      VARCHAR,
    author_position  VARCHAR,
    institution_id   VARCHAR,
    institution_name VARCHAR
);

CREATE TABLE IF NOT EXISTS citations (
    work_id            VARCHAR,
    referenced_work_id VARCHAR
);

CREATE TABLE IF NOT EXISTS topics_meta (
    topic_id      VARCHAR PRIMARY KEY,
    display_name  VARCHAR,
    subfield_id   VARCHAR,
    subfield_name VARCHAR,
    works_count   INTEGER
);

-- Precomputed analytics tables
CREATE TABLE IF NOT EXISTS topic_year_stats (
    topic_id       VARCHAR,
    topic_name     VARCHAR,
    year           INTEGER,
    work_count     INTEGER,
    citation_sum   BIGINT,
    growth_rate    DOUBLE,
    relative_share DOUBLE,
    momentum       DOUBLE,
    is_emerging    BOOLEAN,
    PRIMARY KEY (topic_id, year)
);

CREATE TABLE IF NOT EXISTS emerging_topic_signals (
    topic_id              VARCHAR,
    topic_name            VARCHAR,
    year                  INTEGER,
    acceleration          DOUBLE,
    new_author_fraction   DOUBLE,
    cross_topic_score     DOUBLE,
    composite_score       DOUBLE,
    classification        VARCHAR,
    PRIMARY KEY (topic_id, year)
);

CREATE TABLE IF NOT EXISTS emerging_topic_papers (
    topic_id       VARCHAR,
    year           INTEGER,
    work_id        VARCHAR,
    title          VARCHAR,
    cited_by_count INTEGER,
    rank           INTEGER
);

CREATE TABLE IF NOT EXISTS author_communities (
    author_id       VARCHAR PRIMARY KEY,
    author_name     VARCHAR,
    community_id    INTEGER,
    community_label VARCHAR,
    paper_count     INTEGER
);

CREATE TABLE IF NOT EXISTS community_edges (
    source_author_id VARCHAR,
    target_author_id VARCHAR,
    weight           INTEGER
);

CREATE TABLE IF NOT EXISTS paper_projections (
    work_id    VARCHAR PRIMARY KEY,
    umap_x     DOUBLE,
    umap_y     DOUBLE,
    cluster_id INTEGER
);

-- LDA topic modeling results
CREATE TABLE IF NOT EXISTS lda_topic_words (
    topic_id   INTEGER PRIMARY KEY,
    top_words  VARCHAR,
    label      VARCHAR
);

CREATE TABLE IF NOT EXISTS paper_lda (
    work_id      VARCHAR PRIMARY KEY,
    lda_topic_id INTEGER,
    probability  DOUBLE
);
