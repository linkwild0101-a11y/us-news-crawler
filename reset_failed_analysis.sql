-- 检查有多少文章已分析
SELECT COUNT(*) as total_analyzed 
FROM articles 
WHERE analyzed_at IS NOT NULL;

-- 检查有多少篇文章的聚类是浅层分析 (analysis_depth = 'shallow')
SELECT COUNT(*) as shallow_clusters
FROM analysis_clusters 
WHERE analysis_depth = 'shallow';

-- 查看最近分析的聚类详情
SELECT id, primary_title, analysis_depth, created_at
FROM analysis_clusters 
ORDER BY created_at DESC 
LIMIT 5;
