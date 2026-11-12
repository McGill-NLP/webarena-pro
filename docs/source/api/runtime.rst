Runtime Classes
===============

These classes cover website configuration, task configs, reset contracts,
Docker lifecycle, nginx routing, and auto-login.

Docker
------

.. autoclass:: webarena_pro_core.docker.ContainerInfo

.. autoclass:: webarena_pro_core.docker.DockerContainerManager

Nginx
-----

.. autoclass:: webarena_pro_core.nginx.NginxRoute

.. autoclass:: webarena_pro_core.nginx.NginxProxyManager

Tasks
-----

.. autoclass:: webarena_pro_core.task.WebArenaProTaskConfig

Auto-Login
----------

.. autoclass:: webarena_pro_core.autologin.sync_api.AutoLogin

.. autoclass:: webarena_pro_core.autologin.async_api.AutoLogin

Media
-----

.. automodule:: webarena_pro_media.sync_api
   :members:

.. automodule:: webarena_pro_media.async_api
   :members:
   :exclude-members: MediaClipError, MediaFetchError, TranscriptionError, audio_bytes_to_base64

.. automodule:: webarena_pro_media.audio
   :members:

.. automodule:: webarena_pro_media.video
   :members:

.. automodule:: webarena_pro_media.fetch
   :members:

.. automodule:: webarena_pro_media.binaries
   :members:

UI Evidence
-----------

.. automodule:: webarena_pro_core.eval.ui_evidence
   :members:

.. automodule:: webarena_pro_core.ui_evidence.sync_api
   :members:

.. automodule:: webarena_pro_core.ui_evidence.async_api
   :members:

State Reset
-----------

.. autoclass:: webarena_pro_core.state_reset.SiteRequestTarget

.. autoclass:: webarena_pro_core.state_reset.SiteResetResult

.. autoclass:: webarena_pro_core.state_reset.DockerExecResetSpec
