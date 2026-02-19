-- Add tech category support for rss_sources
-- Run this in Supabase SQL Editor before importing tech sources.

ALTER TABLE rss_sources
DROP CONSTRAINT IF EXISTS rss_sources_category_check;

ALTER TABLE rss_sources
ADD CONSTRAINT rss_sources_category_check
CHECK (category IN ('military', 'politics', 'economy', 'tech'));
