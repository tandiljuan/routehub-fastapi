# SQLite Database Reset

Remove the database (if exist)

```bash
rm -rf routehub.db
```

Create the database

```bash
sqlite3 -bail routehub.db < schema.sqlite.sql
```

Init the database

```bash
sqlite3 -bail routehub.db < init.sqlite.sql
```
