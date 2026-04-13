import duckdb
import matplotlib.pyplot as plt
import os

con = duckdb.connect('data/ai_research.duckdb')

# 1. Plot UMAP Clusters
df = con.execute("SELECT umap_x, umap_y, cluster_id FROM paper_projections").df()

if not df.empty:
    plt.figure(figsize=(10, 8))
    scatter = plt.scatter(df['umap_x'], df['umap_y'], c=df['cluster_id'], cmap='tab20', alpha=0.7, s=20)
    plt.colorbar(scatter, label='Cluster ID')
    plt.title('UMAP Projection of Paper Abstracts (SPECTER + K-Means)')
    plt.xlabel('UMAP 1')
    plt.ylabel('UMAP 2')
    plt.tight_layout()
    plt.savefig('clusters.png', dpi=150)
    print("Saved clusters.png")
else:
    print("No projection data found.")

# 2. Extract LDA Topics
lda_topics = con.execute("SELECT topic_id, label, top_words FROM lda_topic_words ORDER BY topic_id").fetchall()
with open('lda_topics.md', 'w') as f:
    f.write('### LDA Topics Generated\n\n')
    for tid, label, words in lda_topics:
        f.write(f"- **Topic {tid}** [{label}]: {words}\n")
print("Saved lda_topics.md")
con.close()
