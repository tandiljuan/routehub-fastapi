rm -rf routehub.db
sqlite3 -bail routehub.db < schema.sqlite.sql
sqlite3 -bail routehub.db < init.sqlite.sql
