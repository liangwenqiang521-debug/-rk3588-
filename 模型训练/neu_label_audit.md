# NEU 标签审计 200 张（自动统计层）
抽样: 每类 33 张，共 198 张（固定随机种子 42，可复现）
图片尺寸: 200×200
数据源: `datasets/neu_det/images/train`

## 1. 跨类现象（同一图被标多种类）
| 类对 | 图数 |
|---|---:|
| patches + pitted_surface | 9 |
| inclusion + patches | 4 |
| inclusion + scratches | 3 |
| crazing + inclusion | 1 |
| inclusion + pitted_surface | 1 |

**总跨类图: 18 张**

典型跨类图（建议人工核对）：

- `crazing_105.jpg` 主类=crazing, 含=['crazing', 'inclusion'], 框=4
- `patches_265.jpg` 主类=patches, 含=['inclusion', 'patches'], 框=4
- `patches_176.jpg` 主类=patches, 含=['inclusion', 'patches'], 框=5
- `patches_201.jpg` 主类=patches, 含=['inclusion', 'patches'], 框=4
- `patches_202.jpg` 主类=patches, 含=['inclusion', 'patches'], 框=5
- `pitted_surface_294.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=3
- `pitted_surface_291.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=2
- `pitted_surface_155.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=4
- `pitted_surface_258.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=2
- `pitted_surface_174.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=4
- `pitted_surface_237.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=2
- `pitted_surface_292.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=4
- `pitted_surface_197.jpg` 主类=pitted_surface, 含=['inclusion', 'pitted_surface'], 框=3
- `pitted_surface_166.jpg` 主类=pitted_surface, 含=['patches', 'pitted_surface'], 框=3
- `scratches_231.jpg` 主类=scratches, 含=['inclusion', 'scratches'], 框=4
- `scratches_32.jpg` 主类=scratches, 含=['inclusion', 'scratches'], 框=4
- `scratches_97.jpg` 主类=scratches, 含=['inclusion', 'scratches'], 框=3
- `scratches_228.jpg` 主类=scratches, 含=['patches', 'pitted_surface', 'scratches'], 框=3

## 2. 极小框（<5×5 像素）
✅ 未发现 < 5×5 像素的异常小框。

## 3. 框在图边（<2 像素）
共 245 个贴边框（前 20）：

- `crazing_288.jpg` cls=crazing box=(1,3)-(95,85)
- `crazing_13.jpg` cls=crazing box=(1,126)-(89,176)
- `crazing_13.jpg` cls=crazing box=(124,117)-(199,173)
- `crazing_105.jpg` cls=crazing box=(133,1)-(197,149)
- `crazing_105.jpg` cls=crazing box=(59,1)-(197,45)
- `crazing_177.jpg` cls=crazing box=(8,140)-(149,199)
- `crazing_163.jpg` cls=crazing box=(1,86)-(69,185)
- `crazing_136.jpg` cls=crazing box=(1,88)-(88,144)
- `crazing_41.jpg` cls=crazing box=(10,1)-(197,52)
- `crazing_126.jpg` cls=crazing box=(1,63)-(108,124)
- `crazing_299.jpg` cls=crazing box=(3,1)-(200,42)
- `crazing_96.jpg` cls=crazing box=(1,9)-(135,106)
- `crazing_96.jpg` cls=crazing box=(1,145)-(88,200)
- `crazing_262.jpg` cls=crazing box=(1,89)-(62,151)
- `crazing_120.jpg` cls=crazing box=(106,68)-(200,108)
- `crazing_120.jpg` cls=crazing box=(1,81)-(117,146)
- `crazing_120.jpg` cls=crazing box=(1,81)-(117,146)
- `crazing_120.jpg` cls=crazing box=(91,110)-(199,152)
- `crazing_275.jpg` cls=crazing box=(58,53)-(200,169)
- `crazing_224.jpg` cls=crazing box=(1,97)-(122,188)

## 4. 同图近距多框（中心 < 8px，疑似重复标）
共 1 对疑似重复：

- `crazing_120.jpg` 框2,3 距=0.0px

## 5. 抽样清单（完整 198 张）
| 文件 | 主类 | 框数 | 含类 |
|---|---|---:|---|
| `crazing_288.jpg` | crazing | 2 | crazing |
| `crazing_13.jpg` | crazing | 3 | crazing |
| `crazing_105.jpg` | crazing | 4 | crazing,inclusion |
| `crazing_42.jpg` | crazing | 1 | crazing |
| `crazing_177.jpg` | crazing | 3 | crazing |
| `crazing_163.jpg` | crazing | 3 | crazing |
| `crazing_158.jpg` | crazing | 1 | crazing |
| `crazing_136.jpg` | crazing | 2 | crazing |
| `crazing_41.jpg` | crazing | 2 | crazing |
| `crazing_126.jpg` | crazing | 2 | crazing |
| `crazing_299.jpg` | crazing | 4 | crazing |
| `crazing_96.jpg` | crazing | 3 | crazing |
| `crazing_262.jpg` | crazing | 3 | crazing |
| `crazing_120.jpg` | crazing | 5 | crazing |
| `crazing_275.jpg` | crazing | 3 | crazing |
| `crazing_224.jpg` | crazing | 3 | crazing |
| `crazing_107.jpg` | crazing | 3 | crazing |
| `crazing_106.jpg` | crazing | 3 | crazing |
| `crazing_121.jpg` | crazing | 2 | crazing |
| `crazing_156.jpg` | crazing | 3 | crazing |
| `crazing_16.jpg` | crazing | 2 | crazing |
| `crazing_251.jpg` | crazing | 3 | crazing |
| `crazing_278.jpg` | crazing | 4 | crazing |
| `crazing_97.jpg` | crazing | 3 | crazing |
| `crazing_267.jpg` | crazing | 3 | crazing |
| `crazing_151.jpg` | crazing | 1 | crazing |
| `crazing_37.jpg` | crazing | 1 | crazing |
| `crazing_290.jpg` | crazing | 3 | crazing |
| `crazing_33.jpg` | crazing | 1 | crazing |
| `crazing_87.jpg` | crazing | 3 | crazing |
| `crazing_223.jpg` | crazing | 2 | crazing |
| `crazing_157.jpg` | crazing | 2 | crazing |
| `crazing_232.jpg` | crazing | 4 | crazing |
| `inclusion_26.jpg` | inclusion | 4 | inclusion |
| `inclusion_174.jpg` | inclusion | 2 | inclusion |
| `inclusion_56.jpg` | inclusion | 2 | inclusion |
| `inclusion_70.jpg` | inclusion | 3 | inclusion |
| `inclusion_101.jpg` | inclusion | 1 | inclusion |
| `inclusion_39.jpg` | inclusion | 3 | inclusion |
| `inclusion_55.jpg` | inclusion | 1 | inclusion |
| `inclusion_143.jpg` | inclusion | 4 | inclusion |
| `inclusion_289.jpg` | inclusion | 4 | inclusion |
| `inclusion_212.jpg` | inclusion | 2 | inclusion |
| `inclusion_192.jpg` | inclusion | 3 | inclusion |
| `inclusion_98.jpg` | inclusion | 1 | inclusion |
| `inclusion_142.jpg` | inclusion | 2 | inclusion |
| `inclusion_159.jpg` | inclusion | 2 | inclusion |
| `inclusion_4.jpg` | inclusion | 2 | inclusion |
| `inclusion_191.jpg` | inclusion | 2 | inclusion |
| `inclusion_127.jpg` | inclusion | 3 | inclusion |
| `inclusion_123.jpg` | inclusion | 2 | inclusion |
| `inclusion_201.jpg` | inclusion | 2 | inclusion |
| `inclusion_124.jpg` | inclusion | 5 | inclusion |
| `inclusion_197.jpg` | inclusion | 1 | inclusion |
| `inclusion_65.jpg` | inclusion | 3 | inclusion |
| `inclusion_194.jpg` | inclusion | 2 | inclusion |
| `inclusion_263.jpg` | inclusion | 2 | inclusion |
| `inclusion_170.jpg` | inclusion | 1 | inclusion |
| `inclusion_91.jpg` | inclusion | 4 | inclusion |
| `inclusion_112.jpg` | inclusion | 3 | inclusion |
| `inclusion_3.jpg` | inclusion | 3 | inclusion |
| `inclusion_222.jpg` | inclusion | 2 | inclusion |
| `inclusion_247.jpg` | inclusion | 1 | inclusion |
| `inclusion_131.jpg` | inclusion | 1 | inclusion |
| `inclusion_200.jpg` | inclusion | 1 | inclusion |
| `inclusion_120.jpg` | inclusion | 6 | inclusion |
| `patches_257.jpg` | patches | 4 | patches |
| `patches_182.jpg` | patches | 1 | patches |
| `patches_65.jpg` | patches | 1 | patches |
| `patches_280.jpg` | patches | 2 | patches |
| `patches_279.jpg` | patches | 3 | patches |
| `patches_8.jpg` | patches | 3 | patches |
| `patches_73.jpg` | patches | 3 | patches |
| `patches_200.jpg` | patches | 2 | patches |
| `patches_265.jpg` | patches | 4 | inclusion,patches |
| `patches_152.jpg` | patches | 6 | patches |
| `patches_31.jpg` | patches | 2 | patches |
| `patches_115.jpg` | patches | 4 | patches |
| `patches_11.jpg` | patches | 2 | patches |
| `patches_290.jpg` | patches | 5 | patches |
| `patches_161.jpg` | patches | 1 | patches |
| `patches_49.jpg` | patches | 3 | patches |
| `patches_180.jpg` | patches | 3 | patches |
| `patches_119.jpg` | patches | 3 | patches |
| `patches_71.jpg` | patches | 3 | patches |
| `patches_162.jpg` | patches | 1 | patches |
| `patches_75.jpg` | patches | 2 | patches |
| `patches_127.jpg` | patches | 4 | patches |
| `patches_207.jpg` | patches | 2 | patches |
| `patches_176.jpg` | patches | 5 | inclusion,patches |
| `patches_226.jpg` | patches | 2 | patches |
| `patches_283.jpg` | patches | 4 | patches |
| `patches_67.jpg` | patches | 3 | patches |
| `patches_201.jpg` | patches | 4 | inclusion,patches |
| `patches_143.jpg` | patches | 3 | patches |
| `patches_202.jpg` | patches | 5 | inclusion,patches |
| `patches_2.jpg` | patches | 3 | patches |
| `patches_156.jpg` | patches | 2 | patches |
| `patches_292.jpg` | patches | 5 | patches |
| `pitted_surface_180.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_38.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_32.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_294.jpg` | pitted_surface | 3 | patches,pitted_surface |
| `pitted_surface_124.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_280.jpg` | pitted_surface | 3 | pitted_surface |
| `pitted_surface_291.jpg` | pitted_surface | 2 | patches,pitted_surface |
| `pitted_surface_155.jpg` | pitted_surface | 4 | patches,pitted_surface |
| `pitted_surface_258.jpg` | pitted_surface | 2 | patches,pitted_surface |
| `pitted_surface_44.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_174.jpg` | pitted_surface | 4 | patches,pitted_surface |
| `pitted_surface_152.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_237.jpg` | pitted_surface | 2 | patches,pitted_surface |
| `pitted_surface_213.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_181.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_292.jpg` | pitted_surface | 4 | patches,pitted_surface |
| `pitted_surface_35.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_266.jpg` | pitted_surface | 3 | pitted_surface |
| `pitted_surface_168.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_34.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_197.jpg` | pitted_surface | 3 | inclusion,pitted_surface |
| `pitted_surface_54.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_56.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_118.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_17.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_11.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_64.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_193.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_219.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_99.jpg` | pitted_surface | 1 | pitted_surface |
| `pitted_surface_121.jpg` | pitted_surface | 2 | pitted_surface |
| `pitted_surface_166.jpg` | pitted_surface | 3 | patches,pitted_surface |
| `pitted_surface_27.jpg` | pitted_surface | 2 | pitted_surface |
| `rolled-in_scale_84.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_32.jpg` | rolled-in_scale | 1 | rolled-in_scale |
| `rolled-in_scale_190.jpg` | rolled-in_scale | 3 | rolled-in_scale |
| `rolled-in_scale_161.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_287.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_242.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_213.jpg` | rolled-in_scale | 1 | rolled-in_scale |
| `rolled-in_scale_86.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_282.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_23.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_140.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_177.jpg` | rolled-in_scale | 3 | rolled-in_scale |
| `rolled-in_scale_14.jpg` | rolled-in_scale | 1 | rolled-in_scale |
| `rolled-in_scale_172.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_41.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_260.jpg` | rolled-in_scale | 3 | rolled-in_scale |
| `rolled-in_scale_253.jpg` | rolled-in_scale | 1 | rolled-in_scale |
| `rolled-in_scale_98.jpg` | rolled-in_scale | 3 | rolled-in_scale |
| `rolled-in_scale_42.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_267.jpg` | rolled-in_scale | 3 | rolled-in_scale |
| `rolled-in_scale_221.jpg` | rolled-in_scale | 1 | rolled-in_scale |
| `rolled-in_scale_76.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_214.jpg` | rolled-in_scale | 4 | rolled-in_scale |
| `rolled-in_scale_202.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_163.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_83.jpg` | rolled-in_scale | 3 | rolled-in_scale |
| `rolled-in_scale_245.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_241.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_126.jpg` | rolled-in_scale | 4 | rolled-in_scale |
| `rolled-in_scale_45.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_113.jpg` | rolled-in_scale | 3 | rolled-in_scale |
| `rolled-in_scale_133.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `rolled-in_scale_143.jpg` | rolled-in_scale | 2 | rolled-in_scale |
| `scratches_28.jpg` | scratches | 2 | scratches |
| `scratches_145.jpg` | scratches | 2 | scratches |
| `scratches_55.jpg` | scratches | 1 | scratches |
| `scratches_294.jpg` | scratches | 3 | scratches |
| `scratches_218.jpg` | scratches | 4 | scratches |
| `scratches_266.jpg` | scratches | 2 | scratches |
| `scratches_119.jpg` | scratches | 2 | scratches |
| `scratches_207.jpg` | scratches | 2 | scratches |
| `scratches_206.jpg` | scratches | 2 | scratches |
| `scratches_91.jpg` | scratches | 1 | scratches |
| `scratches_231.jpg` | scratches | 4 | inclusion,scratches |
| `scratches_247.jpg` | scratches | 2 | scratches |
| `scratches_168.jpg` | scratches | 3 | scratches |
| `scratches_252.jpg` | scratches | 2 | scratches |
| `scratches_78.jpg` | scratches | 3 | scratches |
| `scratches_103.jpg` | scratches | 1 | scratches |
| `scratches_95.jpg` | scratches | 1 | scratches |
| `scratches_32.jpg` | scratches | 4 | inclusion,scratches |
| `scratches_134.jpg` | scratches | 1 | scratches |
| `scratches_73.jpg` | scratches | 1 | scratches |
| `scratches_249.jpg` | scratches | 1 | scratches |
| `scratches_4.jpg` | scratches | 1 | scratches |
| `scratches_174.jpg` | scratches | 3 | scratches |
| `scratches_46.jpg` | scratches | 1 | scratches |
| `scratches_284.jpg` | scratches | 2 | scratches |
| `scratches_196.jpg` | scratches | 1 | scratches |
| `scratches_133.jpg` | scratches | 1 | scratches |
| `scratches_183.jpg` | scratches | 2 | scratches |
| `scratches_220.jpg` | scratches | 3 | scratches |
| `scratches_97.jpg` | scratches | 3 | inclusion,scratches |
| `scratches_228.jpg` | scratches | 3 | patches,pitted_surface,scratches |
| `scratches_100.jpg` | scratches | 1 | scratches |
| `scratches_72.jpg` | scratches | 1 | scratches |
