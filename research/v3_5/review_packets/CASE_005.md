# CASE_005 — V3.5 Master Case Human Review Packet

Packet Version: `v3.5-review-packet-v1`

## Review Instructions

请基于完整 Raw Transcript 做判断。

V3 Chunk、Existing Interval、Search Hit、Keyword Location 仅用于导航，不限制可标注范围。

不要因为标题、AI Summary 或 Search Rank 判断正文是否支持 Query。

**Navigation Aid Only — Not Annotation Boundary**

## Case Metadata

- Case ID: `CASE_005`
- Scope: `query_video`
- Query: 哪些内容讨论了 Agent 评测信号设计？
- Query language/type: `mixed` / `semantic_question`
- Target video: `51` / `BV1qhE26VEbS`
- Source state/type/language: `readable_raw` / `asr` / `zh`
- Source artifact ID: `source_artifact_5d8f70d93d3e156fd71543d631c201ea5fc347b0ad78278952ebaa9a3cdecf60`
- Source version: `49d36c9f837d144bb00760a41ea84204defddf89f174a45ddb5d486a0b71a338`
- Timeline status: `valid_single_run`
- Sampling stratum: `possible_partial` (sampling hypothesis only; not Gold)
- Case origin: `v3_relevant_evidence`

## Navigation Aids

**Navigation Aid Only — Not Annotation Boundary**

```json
[
  {
    "aid_type": "v3_search_diagnostic",
    "label": "Navigation Aid Only — Not Annotation Boundary",
    "details": {
      "best_rank": 1,
      "appeared_in_modes": [
        "dense",
        "hybrid"
      ],
      "window_ranges": [
        [
          0.03,
          232.59
        ]
      ]
    }
  }
]
```

## Full Raw Transcript

The following JSONL contains every Raw Segment in original Artifact order. No window or navigation aid limits annotation.

<!-- SOURCE_VERSION=49d36c9f837d144bb00760a41ea84204defddf89f174a45ddb5d486a0b71a338 -->
<!-- SEGMENT_COUNT=42 -->
<!-- SEGMENT_ID_LIST_SHA256=464638e8b92de9aebe0a5b1cde7f496380bb2cc169882042b1d1d9a06dcaf560 -->

### Timeline Run `timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be`

Run ordinal `0`; original ordinals `0–41`; segments `42`.

```jsonl
{"original_ordinal":0,"segment_id":"segment_f0b22266a1b00dc45286b88791c1518660b6413a6ad149584f78074a7ecebaa7","start_time":0.03,"end_time":10.08,"source_text":"说起来大家可能不信啊，做A金的平台这一年最难的不是模型选型，不是架构设计，不是调提示词啊，最难的就是搞清楚这东西到底多少用，对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":1,"segment_id":"segment_4b9b65664017f8bbd4ca7c2acea5822f10dbc8978a7ef057dae3c74072adaa23","start_time":10.08,"end_time":12.48,"source_text":"也刚刚下班啊，就是为什么呢？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":2,"segment_id":"segment_d16d04ada5d76e3a6c193d1f1f1fc8f6dbc3f4d80feb6a9fb6bdd44926779ac1","start_time":13.0,"end_time":18.28,"source_text":"因为你给A进一个任务啊，他跑完了你怎么判断他跑的不好？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":3,"segment_id":"segment_23fab2db11a58e843bf05cd264b74560626a0b03d6a1199e540cf73c919c47b2","start_time":18.28,"end_time":25.64,"source_text":"靠感觉，靠人工一个人看，还随便打个脚本打个分啊啊，我在这上面我们在这上面踩坑太多了。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":4,"segment_id":"segment_1495cdc55ef6e6a068e0626e7eddad1f6e97cfb21313735b64244b302fdbfd25","start_time":25.64,"end_time":34.66,"source_text":"就是首先啊我们的平台支持搭插件、挂吃库、编盘啊，但是呢然后一键发布成A I或者对话应用，听起来挺好的对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":5,"segment_id":"segment_32b2d2c095b7228ee5742c5eece8184db9e421d192f21cf7a5654891c131aa42","start_time":34.66,"end_time":38.57,"source_text":"但是呢好不好用啊，你得有东西办法量出来。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":6,"segment_id":"segment_f2762ed7f148c4840374bdac59ec2623862b40e73d08e5561c64fb7d67e43b1b","start_time":38.57,"end_time":44.9,"source_text":"我们一开始的评测方法非常原始啊，就手动跑几十个任务，看按键的输出啊，凭感觉打分。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":7,"segment_id":"segment_6d21e6c5bdc7ca9b74fa371446b4e4e9ed6331e0170e78e98111c4f82bbeaa0b","start_time":45.29,"end_time":46.26,"source_text":"你说这样靠谱吗？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":8,"segment_id":"segment_a724a60483fac6c30c8cf7a6f5ac2a6f50227e3d5595a2e4389b716a34d157fa","start_time":47.2,"end_time":48.59,"source_text":"显然不靠谱啊，对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":9,"segment_id":"segment_88bd472873fe03e08293d44b3e99aff34adf91d5e21addf7ca7749560967b27e","start_time":49.71,"end_time":56.4,"source_text":"就是说所以说这个evo做的越早越好，我们管这个叫什么第零部对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":10,"segment_id":"segment_e443a0a94601084862071a9bfe17f2c6ab4474ebe4999f67f86e4e976ada5b29","start_time":56.4,"end_time":60.32,"source_text":"他不需要你有几百个测试用例，20到50个真实场景就够了。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":11,"segment_id":"segment_2dae89a7722d3c4eaa501783641d9348618efefe09d6b649e04f1c8ded4c72a9","start_time":61.25,"end_time":64.9,"source_text":"然后呢，说到这个评测指标，很多人只听过这个PaaS k对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":12,"segment_id":"segment_53d8ff1c2a31f74edcb812a17956a48be5e4d9b839c674f4d22683ae5dbdf61c","start_time":64.9,"end_time":67.22,"source_text":"另一个指标叫passport k对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":13,"segment_id":"segment_03b4f6049a2f41ba8d7f87229a3922e5ed553a898c996def0d5e31d7698e432a","start_time":67.22,"end_time":68.92,"source_text":"看着像，但是不是一回事。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":14,"segment_id":"segment_7c7bce0b5fd03056a5cb216a48bef599e4dd43af3cdafcbf755ed1c1f442d0f9","start_time":68.92,"end_time":72.53,"source_text":"那PaaS k是你跑K一次，只要有一次通过就算过。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":15,"segment_id":"segment_6186b34e8a3f08e2e180a04dd71ecc88747c7a1bc552cf304f27b3c75985acd0","start_time":73.13,"end_time":85.2,"source_text":"那part k呢是你跑K一次必须K次全过才算过，那这个区别就太大了啊，我给你举个例子，我们那个元气有个场景就是让A根据用户上传的文档自动做知识问答。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":16,"segment_id":"segment_58c7e4a74766d6a414616766b9019ab28a1b80d0e920c3e5906488f8034ffe7d","start_time":85.43,"end_time":89.71,"source_text":"你用PaaS艾十来测，准确率能达90%以上。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":17,"segment_id":"segment_f53b5efc409be1c3058de0dd65e7d3de7c1166cc298ee40cbbdd6f0736184200","start_time":90.21,"end_time":94.96,"source_text":"看着数据很好，但是切换到PaaS power 10的话，直接掉到不到50%，发现了吗？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":18,"segment_id":"segment_b557dc6d3e1dec3affb09fbcdc5633bbe65c182ac56cf8959becd4aa6c16700b","start_time":95.33,"end_time":107.74,"source_text":"啊，PaaS可测的是你这个A的能力上限，PaaS power可测的是稳定性啊，能力上限高不稳定那就是有问题的那我们后来定两个指标，都看日常开发，我们迭代看K对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":19,"segment_id":"segment_902693c44d606052d658e6b966cdd6b1d644292c04d48616c9caefee4a7ef45f","start_time":108.09,"end_time":113.52,"source_text":"们没有把能力上限拉下去，版之前呢必须要跑PaaS power，对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":20,"segment_id":"segment_038cd28ddb32634cff3da9123786685d4fe4dd2fd286bc85202b1d9ca3469b67","start_time":113.52,"end_time":119.14,"source_text":"不稳定的版本绝对不能上线，把这个策略写进了我们的流程里面，效果非常明显。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":21,"segment_id":"segment_6110c7f90ccc8b74aff505f51e03a1f630c4cc2374c8f11d1db369543da4530b","start_time":123.67,"end_time":134.98,"source_text":"那还有一些我觉得比较ok的地方就是首先啊任务的描述在评测里面，任务描述一定要写的没有歧义，并且要非常参考答案啊。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":22,"segment_id":"segment_eb790eb8ba926349129340c34be0dd375496b008f2eb02e7bd3b7ddc13e2ec2e","start_time":134.98,"end_time":145.56,"source_text":"因为你说清楚了，你觉得说清楚很多是模糊地带，我们后来搞一套模板，每个任务必须写清楚前置条件、输入格式、预期行为、边界情况，以及什么算通过，什么不通过。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":23,"segment_id":"segment_e321424b9067824c5a0fc0c23f2e2ed744dc52cf99e4093a67e25a6bfd0660d0","start_time":146.01,"end_time":147.75,"source_text":"而且正反案例都要测。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":24,"segment_id":"segment_df38cdc4a676254055c629c3c6d9aefa8f337957dffdaf539e16c89229a8ac92","start_time":147.75,"end_time":155.63,"source_text":"那这个虽然很朴素，但是很多人忽视，很多人只测正常流程，发现这个边界情况没人管，出问题才发现。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":25,"segment_id":"segment_caeff19ad3f2d818f8d050b70792c53a2841bb6fafeb27856a2eb1db2d9d2612","start_time":155.63,"end_time":163.03,"source_text":"啊，我们专专门建了这个navigative test的case库啊，里面全都是给A定的挖坑场景。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":26,"segment_id":"segment_5a598a2ff8c5ac14ef5bc932394045132d87ccbb3b9d9c1165fa4cfcc5b24c11","start_time":163.14,"end_time":169.78,"source_text":"比如说注入恶意的指令，这个很真实了，很多场景用户都会注入恶意指令的，他会对不对？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":27,"segment_id":"segment_a076bca422338786ed737ae0ee25ba67a6fa3cd710c412e4cbc008c5d68bcead","start_time":169.78,"end_time":170.02,"source_text":"对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":28,"segment_id":"segment_76ad00de5680e9731a92c4bdc9dccad74cbc80f0eecca6aed6822871e518f4d8","start_time":170.02,"end_time":175.07,"source_text":"包括给出矛盾需求，抛出语法错误的，然后评测评分期呢不要随便写。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":29,"segment_id":"segment_1df1776d1ab2ee0286f2d722ab4b1b9c3a0813072968f596f16d6dc7ff87c0e5","start_time":175.07,"end_time":178.02,"source_text":"我们早期用了正则匹配来判定A进的输出对不对？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":30,"segment_id":"segment_ccbffa90fbdbabefe4b06dd0b5de17828a3c9a117e7331dda53f4267afc53db8","start_time":178.48,"end_time":182.61,"source_text":"那发现很多正确答案被判为错误，因表达方式不一致，但是是对的。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":31,"segment_id":"segment_73fd0bc52c35b555a7b3c9b3f9115b8e6a7376105c4ad76a3111117d645a38d4","start_time":183.0,"end_time":187.47,"source_text":"后来换成价值，加上这个人工抽检结合整高很多。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":32,"segment_id":"segment_623d89dea5ba1194149111373680543c6210d38de56578179515a42773de96e8","start_time":188.65,"end_time":194.12,"source_text":"然后读transcript不要看数字，我特别认同啊，很多次我们看这个指标绝得没问题。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":33,"segment_id":"segment_b96f46dc77db2d332c290429bdcd5d4dc55afcb2943b243703c0eeed48e67211","start_time":194.12,"end_time":205.78,"source_text":"一翻A进对话材照中间绕多少弯路，做了的无庸功transcript才了解A键的真实那个窗口啊，还有话就是这个评测不能扔，就是设置完就扔那儿啊。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":34,"segment_id":"segment_7566d825078442af299642021b3f3ccac8c59056bf0f3913b80fd7b702f213ee","start_time":205.78,"end_time":212.34,"source_text":"随着模型的迭代，很多问题现在拦不住了，评测就饱和了，我们得持续上难度，对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":35,"segment_id":"segment_e680059e86cc1af52b329900b21d8d5d8fbba92a91249be861d321a767d2938b","start_time":212.34,"end_time":217.4,"source_text":"我们专门有人去看评测报告，标记哪些case太简单，哪些该换掉了。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":36,"segment_id":"segment_8063092c880e74efe6ff4430890e39410a4c7835c3d68b1dce81cc9646c444b6","start_time":218.01,"end_time":226.54,"source_text":"那整个流程做下来最大的收获不是计算手，而是一个人能不能准确评估自己的能力，跟一个A能不能通过E底层是相通的对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":37,"segment_id":"segment_e31b515ac8126f60b73c907add9ad7a1f36433e045d6f1eb844f39bb30c9ec1f","start_time":226.54,"end_time":232.59,"source_text":"比如说你写简历的时候，你怎么判断一项技术自己是懂熟练还是了解面试之前怎么知道水平够不够。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":38,"segment_id":"segment_c1d1d3e60f5a0bf25b4e249fe13e9591fb219af8623bea2cb398f1e6e0a29c54","start_time":232.88,"end_time":248.08,"source_text":"很多人写简历的时候什么都敢写，面试官一问都露馅，就是典型的PaaS k自信，换个问法就不行了，真正能力就是PaaS part那种每次都能拿下的逻定写啊，其实我觉得现在我做的这种简历面试辅导报求跟做A的评测很似很相似。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":39,"segment_id":"segment_5352b936229a56560ddf7b3e8cb98dfab6f6a273da235c3163a7df963859141a","start_time":248.4,"end_time":252.87,"source_text":"这个简历优化不是帮你把简历写的好看，而是帮你发现有哪些问题你表达好，对吧？","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":40,"segment_id":"segment_18155c1b93b4384281d0225fde39772763537206d6f05b9a0a35f8afb69d631d","start_time":252.87,"end_time":260.74,"source_text":"找到自己知识编辑补齐啊，其实搞清楚自己行不行，不管是做评测还是找工作都是很重要的啊。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
{"original_ordinal":41,"segment_id":"segment_0d099bfe7603ace61c68b430a139d3331f34e113e6eaa79fd1c56e7f9950dd73","start_time":260.74,"end_time":263.77,"source_text":"你有需要呃简历面辅杂或者学会法，可以直接找我报名。","timeline_run_id":"timeline_run_e2cc938370396dc4eb7cac939fb4e6a37df508e9ef93ea963a3c5028469c49be","evidence_eligible":true}
```

## Human Decision Form

Decision Status:
unreviewed

Required Aspects:
- 

Gold Evidence Groups:
- 

Sufficiency Label:
unreviewed

Supported Aspects:
- 

Missing Aspects:
- 

Conflict Notes:


Primary Reason Codes:
- 

Support Notes:


Review Confidence:
high / medium / low

Needs Second Review:
yes / no

Reviewer Flags:
- 
