CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    password_hash TEXT,
    display_name TEXT,
    bio TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tweets (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    content TEXT,
    quote_tweet_id TEXT,
    reply_to_id TEXT,
    view_count INTEGER NOT NULL DEFAULT 0,
    source_reply_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (quote_tweet_id) REFERENCES tweets(id),
    FOREIGN KEY (reply_to_id) REFERENCES tweets(id)
);

CREATE TABLE IF NOT EXISTS follows (
    follower_id TEXT,
    followed_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (follower_id, followed_id),
    FOREIGN KEY (follower_id) REFERENCES users(id),
    FOREIGN KEY (followed_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS likes (
    user_id TEXT,
    tweet_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, tweet_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (tweet_id) REFERENCES tweets(id)
);

CREATE TABLE IF NOT EXISTS bookmarks (
    user_id TEXT,
    tweet_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, tweet_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (tweet_id) REFERENCES tweets(id)
);

CREATE TABLE IF NOT EXISTS retweets (
    user_id TEXT,
    tweet_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, tweet_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (tweet_id) REFERENCES tweets(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    sender_id TEXT,
    receiver_id TEXT,
    content TEXT,
    read_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id),
    FOREIGN KEY (receiver_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS group_chats (
    id TEXT PRIMARY KEY,
    name TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS group_chat_members (
    chat_id TEXT,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES group_chats(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS group_messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT,
    sender_id TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES group_chats(id),
    FOREIGN KEY (sender_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_view_count ON tweets(view_count DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_reply_to_id ON tweets(reply_to_id);
CREATE INDEX IF NOT EXISTS idx_tweets_user_id ON tweets(user_id);
CREATE INDEX IF NOT EXISTS idx_likes_tweet_id ON likes(tweet_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_tweet_id ON bookmarks(tweet_id);
CREATE INDEX IF NOT EXISTS idx_retweets_tweet_id ON retweets(tweet_id);
