-- Finalize the dataset backfill without disturbing task-bearing seed messages.
-- Run after importing existing_channel_backfill_seed.json and before pg_dump.

BEGIN;

-- Apply the source dataset dates (and the one explicitly fixed task-state DM
-- date) after Mattermost's API has created the posts with wall-clock dates.
UPDATE posts
SET createat = (props ->> 'source_create_at_ms')::bigint,
    updateat = (props ->> 'source_create_at_ms')::bigint,
    editat = 0
WHERE props ->> 'seed_batch' = 'existing-channel-backfill-v1';

-- API creation updated channel timestamps before the post dates were fixed.
-- Recompute all post-derived channel counters so the UI and unread math agree.
WITH post_stats AS (
    SELECT
        channelid,
        count(*) FILTER (WHERE deleteat = 0) AS total_count,
        count(*) FILTER (WHERE deleteat = 0 AND rootid = '') AS root_count,
        coalesce(max(createat) FILTER (WHERE deleteat = 0), 0) AS last_post_at,
        coalesce(max(createat) FILTER (WHERE deleteat = 0 AND rootid = ''), 0)
            AS last_root_post_at
    FROM posts
    GROUP BY channelid
)
UPDATE channels AS channel
SET totalmsgcount = post_stats.total_count,
    totalmsgcountroot = post_stats.root_count,
    lastpostat = post_stats.last_post_at,
    lastrootpostat = post_stats.last_root_post_at
FROM post_stats
WHERE channel.id = post_stats.channelid;

-- Fifty public/private team channels remain globally. The admin task user is
-- joined only to the 14 task-relevant team channels below. With the two seeded
-- group DMs and the fixed Emma DM, this is 17 joined conversations in total.
DELETE FROM channelmembers AS membership
USING users AS task_user, channels AS channel
WHERE task_user.username = 'admin'
  AND membership.userid = task_user.id
  AND membership.channelid = channel.id
  AND channel.type IN ('O', 'P')
  AND channel.name NOT IN (
      'project-alpha',
      'project-beta',
      'deployments',
      'code-reviews',
      'bugs-and-issues',
      'standup-notes',
      'tech-discussions',
      'devops',
      'security-alerts',
      'campaigns',
      'analytics',
      'announcements',
      'watercooler',
      'events'
  );

-- Start with every joined conversation read.
UPDATE channelmembers AS membership
SET lastviewedat = channel.lastpostat,
    msgcount = channel.totalmsgcount,
    mentioncount = 0,
    lastupdateat = channel.lastpostat,
    msgcountroot = channel.totalmsgcountroot,
    mentioncountroot = 0,
    urgentmentioncount = 0
FROM channels AS channel, users AS task_user
WHERE task_user.username = 'admin'
  AND membership.userid = task_user.id
  AND membership.channelid = channel.id;

-- Leave exactly one unread message in seven task-relevant team channels and in
-- the admin/Emma DM: eight unread messages total, safely below the limit of 20.
WITH task_user AS (
    SELECT id FROM users WHERE username = 'admin'
),
selected_channels AS (
    SELECT channel.id
    FROM channels AS channel
    WHERE channel.type IN ('O', 'P')
      AND channel.name IN (
          'project-alpha',
          'project-beta',
          'deployments',
          'code-reviews',
          'analytics',
          'announcements',
          'events'
      )
    UNION ALL
    SELECT channel.id
    FROM channels AS channel
    WHERE channel.type = 'D'
      AND EXISTS (
          SELECT 1
          FROM channelmembers AS member
          JOIN users AS user_record ON user_record.id = member.userid
          WHERE member.channelid = channel.id AND user_record.username = 'admin'
      )
      AND EXISTS (
          SELECT 1
          FROM channelmembers AS member
          JOIN users AS user_record ON user_record.id = member.userid
          WHERE member.channelid = channel.id AND user_record.username = 'emma.davis'
      )
),
unread_state AS (
    SELECT
        channel.id,
        greatest(channel.totalmsgcount - 1, 0) AS read_count,
        coalesce(
            (
                SELECT max(post.createat)
                FROM posts AS post
                WHERE post.channelid = channel.id
                  AND post.deleteat = 0
                  AND post.createat < channel.lastpostat
            ),
            channel.createat
        ) AS last_viewed_at
    FROM channels AS channel
    JOIN selected_channels ON selected_channels.id = channel.id
)
UPDATE channelmembers AS membership
SET msgcount = unread_state.read_count,
    lastviewedat = unread_state.last_viewed_at,
    lastupdateat = unread_state.last_viewed_at
FROM unread_state, task_user
WHERE membership.userid = task_user.id
  AND membership.channelid = unread_state.id;

-- Fail loudly if a future seed change violates any requested invariant.
DO $$
DECLARE
    backfill_count bigint;
    visible_channel_count bigint;
    joined_team_channel_count bigint;
    joined_conversation_count bigint;
    unread_count bigint;
    protected_count bigint;
    rank_mismatch_count bigint;
    recent_emma_count bigint;
BEGIN
    SELECT count(*) INTO backfill_count
    FROM posts
    WHERE props ->> 'seed_batch' = 'existing-channel-backfill-v1';
    IF backfill_count < 5000 THEN
        RAISE EXCEPTION 'Expected at least 5000 existing-channel backfill posts, got %', backfill_count;
    END IF;

    SELECT count(*) INTO visible_channel_count
    FROM channels
    WHERE deleteat = 0 AND type IN ('O', 'P');
    IF visible_channel_count <> 50 THEN
        RAISE EXCEPTION 'Expected 50 visible team channels, got %', visible_channel_count;
    END IF;

    SELECT count(*) INTO joined_team_channel_count
    FROM channelmembers AS membership
    JOIN users AS task_user ON task_user.id = membership.userid
    JOIN channels AS channel ON channel.id = membership.channelid
    WHERE task_user.username = 'admin' AND channel.type IN ('O', 'P');
    IF joined_team_channel_count <> 14 THEN
        RAISE EXCEPTION 'Expected admin in 14 team channels, got %', joined_team_channel_count;
    END IF;

    SELECT count(*) INTO joined_conversation_count
    FROM channelmembers AS membership
    JOIN users AS task_user ON task_user.id = membership.userid
    WHERE task_user.username = 'admin';
    IF joined_conversation_count >= 20 THEN
        RAISE EXCEPTION 'Admin must be joined to fewer than 20 conversations, got %', joined_conversation_count;
    END IF;

    SELECT coalesce(sum(channel.totalmsgcount - membership.msgcount), 0)
    INTO unread_count
    FROM channelmembers AS membership
    JOIN users AS task_user ON task_user.id = membership.userid
    JOIN channels AS channel ON channel.id = membership.channelid
    WHERE task_user.username = 'admin';
    IF unread_count <> 8 OR unread_count >= 20 THEN
        RAISE EXCEPTION 'Expected exactly 8 unread messages and fewer than 20, got %', unread_count;
    END IF;

    SELECT count(*) INTO protected_count
    FROM posts
    WHERE id IN (
        'zs7apgtgpfn3bnxr9cxznwjpry', 'suwnzum7ppn5tbeag1ga6k1r7w',
        'i9a9qqzfginezb1o6b8a3siuoh', 'hhigzptwetywzb3g7hhhhjdw8e',
        'rtdewtn5ein8uqwxqjq71jkiqh', 'rrdusfgbf3gf7qrahwjai64wuw',
        'u9b7ehb3kbnz5dkohhn3s6rt9y', 'dmpbf4epffrkmd9biy83m5qitw',
        '8p613yhn3tr5zjiuy8ebxazfih', '7c9cox7rttg4bb1jx4fmrrmz8h',
        'zj5n1igz83g7bnoujg81u9c9kh', 'bfyx5zu8k7b45mkmhe4ex4srwc',
        'czed4ajgb7byjbpg854mikegzy', 'cm7g4nhuyjbq9fr1furyz7emph',
        'oq4um7bawtd48fr4tfchj6zkce', 'zgcemj5typgct8zb5mh4a7kxue',
        'duk3c7xk9bnemr57t3kda66zwh', '4hnjptbpmpnmzgdqdth51qxt3y'
    ) AND deleteat = 0;
    IF protected_count <> 18 THEN
        RAISE EXCEPTION 'Expected all 18 original protected posts, got %', protected_count;
    END IF;

    WITH expected(id, expected_rank) AS (
        VALUES
            ('zs7apgtgpfn3bnxr9cxznwjpry', 4),
            ('suwnzum7ppn5tbeag1ga6k1r7w', 17),
            ('i9a9qqzfginezb1o6b8a3siuoh', 4),
            ('hhigzptwetywzb3g7hhhhjdw8e', 1),
            ('rtdewtn5ein8uqwxqjq71jkiqh', 9),
            ('rrdusfgbf3gf7qrahwjai64wuw', 7),
            ('u9b7ehb3kbnz5dkohhn3s6rt9y', 3),
            ('dmpbf4epffrkmd9biy83m5qitw', 5),
            ('8p613yhn3tr5zjiuy8ebxazfih', 7),
            ('7c9cox7rttg4bb1jx4fmrrmz8h', 1),
            ('zj5n1igz83g7bnoujg81u9c9kh', 11),
            ('bfyx5zu8k7b45mkmhe4ex4srwc', 5),
            ('czed4ajgb7byjbpg854mikegzy', 3),
            ('cm7g4nhuyjbq9fr1furyz7emph', 5),
            ('oq4um7bawtd48fr4tfchj6zkce', 9),
            ('zgcemj5typgct8zb5mh4a7kxue', 4),
            ('duk3c7xk9bnemr57t3kda66zwh', 5),
            ('4hnjptbpmpnmzgdqdth51qxt3y', 5)
    ),
    actual AS (
        SELECT
            protected.id,
            (
                SELECT count(*) + 1
                FROM posts AS newer
                WHERE newer.channelid = protected.channelid
                  AND newer.deleteat = 0
                  AND (
                      newer.createat > protected.createat
                      OR (newer.createat = protected.createat AND newer.id > protected.id)
                  )
            ) AS newest_rank
        FROM posts AS protected
        JOIN expected ON expected.id = protected.id
    )
    SELECT count(*) INTO rank_mismatch_count
    FROM actual
    JOIN expected USING (id)
    WHERE actual.newest_rank <> expected.expected_rank
       OR actual.newest_rank > 100;
    IF rank_mismatch_count <> 0 THEN
        RAISE EXCEPTION '% protected messages changed rank or left the newest 100', rank_mismatch_count;
    END IF;

    SELECT count(*) INTO recent_emma_count
    FROM posts AS post
    JOIN users AS author ON author.id = post.userid
    WHERE post.props ->> 'task_evidence_key' = 'recent-emma-interaction'
      AND author.username = 'emma.davis';
    IF recent_emma_count <> 1 THEN
        RAISE EXCEPTION 'Expected one fixed recent Emma evidence post, got %', recent_emma_count;
    END IF;
END $$;

COMMIT;
