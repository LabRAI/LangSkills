# Edge cases

- 有些发布只提供 SHA-1/MD5；优先使用提供 SHA-256/签名的渠道。
- `sha256sum -c` 默认校验文件中的路径；若移动了文件，需更新 manifest 或在原路径校验。
