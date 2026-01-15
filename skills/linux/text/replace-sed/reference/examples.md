# Examples

```bash
# Replace only in a section-like prefix
sed -i.bak '/^\[prod\]/,/^\[/ s|http://old|http://new|g' ./app.ini
```
