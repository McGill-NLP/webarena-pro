Evaluation Classes
==================

These classes cover the runner-neutral DAG evaluators, snapshots, step
verifier protocol, and built-in backend snapshot providers.

Snapshots
---------

.. autoclass:: webarena_pro_core.eval.snapshot.Snapshot

.. autoclass:: webarena_pro_core.eval.snapshot.SnapshotDiff

DAG Evaluation
--------------

.. autoclass:: webarena_pro_core.eval.dag.EvalNode

.. autoclass:: webarena_pro_core.eval.dag.EvalDAG

.. autoclass:: webarena_pro_core.eval.dag.NodeResult

.. autoclass:: webarena_pro_core.eval.dag.EvalContext

.. autoclass:: webarena_pro_core.eval.dag.NodeEvaluator

.. autoclass:: webarena_pro_core.eval.dag.DAGEvaluator

Node Evaluators
---------------

.. autoclass:: webarena_pro_core.eval.backend_state.BackendStateEvaluator

.. autoclass:: webarena_pro_core.eval.mattermost_calls.MattermostCallsEvaluator

.. autoclass:: webarena_pro_core.eval.answer_match.AnswerMatchEvaluator

.. autoclass:: webarena_pro_core.eval.file_downloaded.FileDownloadedEvaluator

.. autoclass:: webarena_pro_core.eval.structural.BrowserEventEvaluator

.. autoclass:: webarena_pro_core.eval.structural.UIStateEvaluator

.. autoclass:: webarena_pro_core.eval.llm_judge.LLMJudgeEvaluator

.. autoclass:: webarena_pro_core.eval.tiered.TieredRubricEvaluator

Verifier Protocol
-----------------

.. autoclass:: webarena_pro_core.eval.protocol.EvaluationStepRecord

.. autoclass:: webarena_pro_core.eval.protocol.StepVerifier

.. autoclass:: webarena_pro_core.eval.protocol.EvaluationStepConverter

.. autoclass:: webarena_pro_core.eval.protocol.RubricEvaluationSpec

.. autoclass:: webarena_pro_core.verifier.rubric_verifier.RubricVerifier

Snapshot Providers
------------------

.. autoclass:: webarena_pro_core.eval.providers.SnapshotProvider

.. autoclass:: webarena_pro_core.eval.providers.activity.ActivityLogProvider

.. autoclass:: webarena_pro_core.eval.providers.caldav.CalDAVEventsProvider

.. autoclass:: webarena_pro_core.eval.providers.carddav.CardDAVContactsProvider

.. autoclass:: webarena_pro_core.eval.providers.immich_assets.ImmichAssetsProvider

.. autoclass:: webarena_pro_core.eval.providers.metabase_cards.MetabaseCardsProvider

.. autoclass:: webarena_pro_core.eval.providers.metabase_dashboards.MetabaseDashboardsProvider

.. autoclass:: webarena_pro_core.eval.providers.metabase_timeline_events.MetabaseTimelineEventsProvider

.. autoclass:: webarena_pro_core.eval.providers.mydrive.MyDriveFilesProvider

.. autoclass:: webarena_pro_core.eval.providers.ocs_users.OCSUsersProvider

.. autoclass:: webarena_pro_core.eval.providers.talk.TalkRoomsProvider

.. autoclass:: webarena_pro_core.eval.providers.webdav.WebDAVFilesProvider
