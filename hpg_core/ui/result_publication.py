"""Atomare Veröffentlichung eines Ergebnisses in den Qt-Ansichten."""
from copy import deepcopy
from PyQt6.QtWidgets import QPushButton
from ..run_state import ACTIVE_RUN_STATES


class ResultPublicationMixin:
    """Prepare/Commit und Ressourcenfreigabe; Widget-Fabriken liefert die App."""

    def _connect_publication_signals(self, playlist_panel, mix_tips_panel, toolbar):
        toolbar.generate_clicked.connect(self.start_analysis)
        toolbar.export_clicked.connect(self.export_playlist)
        playlist_panel.export_clicked.connect(self.export_playlist)
        playlist_panel.preview_clicked.connect(self.preview_transitions)
        playlist_panel.restart_clicked.connect(self.restart_app)
        playlist_panel.playlist_reordered.connect(self._on_playlist_reordered)
        playlist_panel.reorder_failed.connect(self._on_playlist_reorder_failed)
        mix_tips_panel.preview_state_changed.connect(self._on_preview_state_changed)
        mix_tips_panel.candidate_chosen.connect(self._on_candidate_chosen)
        mix_tips_panel.reserve_ready.connect(self._on_render_reserve_ready)
        mix_tips_panel.transition_rating_requested.connect(self._rate_transition_preview)

    def _disconnect_publication_signals(self, playlist_panel, mix_tips_panel, toolbar):
        connections = (
            (toolbar.generate_clicked, self.start_analysis),
            (toolbar.export_clicked, self.export_playlist),
            (playlist_panel.export_clicked, self.export_playlist),
            (playlist_panel.preview_clicked, self.preview_transitions),
            (playlist_panel.restart_clicked, self.restart_app),
            (playlist_panel.playlist_reordered, self._on_playlist_reordered),
            (playlist_panel.reorder_failed, self._on_playlist_reorder_failed),
            (mix_tips_panel.preview_state_changed, self._on_preview_state_changed),
            (mix_tips_panel.candidate_chosen, self._on_candidate_chosen),
            (mix_tips_panel.reserve_ready, self._on_render_reserve_ready),
            (mix_tips_panel.transition_rating_requested, self._rate_transition_preview),
        )
        for signal, slot in connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _prepare_uebergangs_views(
        self, playlist, quality_metrics, transition_plan, bpm_tolerance,
        scoring_context, generation_result=None,
    ):
        """Bereitet alle abhaengigen Views ohne Mutation des Live-Zustands vor."""
        PlaylistPanel, MixTipsPanel, TimelinePanel, AnalyticsPanel, ToolbarWidget = self._publication_widget_types()
        playlist_panel = PlaylistPanel()
        mix_tips_panel = MixTipsPanel()
        timeline_panel = TimelinePanel()
        analytics_panel = AnalyticsPanel()
        toolbar = ToolbarWidget()
        prepared = (
            playlist_panel, mix_tips_panel, timeline_panel, analytics_panel, toolbar
        )
        try:
            self._connect_analytics_signals(analytics_panel)
            # Der View-Austausch darf den geoeffneten Hoertest weder vergessen
            # noch laufende Aktionen wieder freigeben. Keine neue Geschaeftsregel.
            for name, button in vars(self.analytics_panel).items():
                if name.startswith("hearing_") and isinstance(button, QPushButton):
                    getattr(analytics_panel, name).setEnabled(button.isEnabled())
            analytics_panel.hearing_status.setText(
                self.analytics_panel.hearing_status.text()
            )
            playlist_panel.set_playlist_data(
                playlist,
                quality_metrics,
                transition_recommendations=transition_plan,
                bpm_tolerance=bpm_tolerance,
                scoring_context=scoring_context,
                generation_result=generation_result,
            )
            playlist_panel.restore_view_from(self.playlist_panel)
            mix_tips_panel.set_recommendations(transition_plan, playlist)
            mix_tips_panel.setup_transition_previews(transition_plan)
            mix_tips_panel._generation_result = generation_result
            timeline_panel.set_timeline(
                playlist, transition_plan, scoring_context
            )
            analytics_panel.set_analytics(
                quality_metrics, playlist, bpm_tolerance,
                transition_plan, scoring_context,
            )
            toolbar.set_info(self.toolbar.info_label.text())
            toolbar.set_run_state(self.run_state)
            toolbar.set_generate_enabled(self.toolbar.generate_btn.isEnabled())
            toolbar.set_export_enabled(self.toolbar.export_btn.isEnabled())
            toolbar.set_quality(quality_metrics.get("overall_score", 0))
            playlist_panel.set_reorder_locked(
                self.run_state in ACTIVE_RUN_STATES
            )
            mix_tips_panel.set_candidate_choices_enabled(
                self.run_state not in ACTIVE_RUN_STATES
            )
            self._connect_publication_signals(
                playlist_panel, mix_tips_panel, toolbar
            )
        except Exception:
            try:
                mix_tips_panel._cleanup_existing_previews()
            except Exception:
                pass
            for widget in prepared:
                widget.deleteLater()
            raise
        return prepared

    def _retire_mix_tips_panel(self, panel):
        """Gibt Preview-Ressourcen nach dem Commit genau einmal frei."""
        running = [worker for worker in panel._render_workers if worker.isRunning()]
        if running:
            self._retired_mix_tips_panels.add(panel)
            for worker in running:
                worker.finished.connect(
                    lambda retired=panel: self._finish_retired_mix_tips_panel(retired)
                )
        try:
            panel._cleanup_existing_previews()
        finally:
            if not any(worker.isRunning() for worker in panel._render_workers):
                self._retired_mix_tips_panels.discard(panel)
                panel.deleteLater()

    def _finish_retired_mix_tips_panel(self, panel):
        if panel._render_worker is not None or panel._render_workers:
            return
        self._retired_mix_tips_panels.discard(panel)
        panel.deleteLater()
        self._try_finish_cancelled_run()

    def _commit_uebergangs_views(
        self, prepared, playlist, quality_metrics, generation_result
    ):
        """Tauscht vorbereitete Widgets strukturell aus und entsorgt danach alte."""
        new_playlist, new_mix, new_timeline, new_analytics, new_toolbar = prepared
        old_panels = (
            self.playlist_panel, self.mix_tips_panel,
            self.timeline_panel, self.analytics_panel,
        )
        new_panels = (new_playlist, new_mix, new_timeline, new_analytics)
        old_toolbar = self.toolbar
        current_index = self.content_stack.currentIndex()
        toolbar_swapped = False
        try:
            for panel in old_panels:
                self.content_stack.removeWidget(panel)
            for index, panel in enumerate(new_panels, start=1):
                self.content_stack.insertWidget(index, panel)
            replaced = self._right_layout.replaceWidget(old_toolbar, new_toolbar)
            if replaced is None:
                raise RuntimeError("Toolbar konnte nicht atomar ersetzt werden")
            toolbar_swapped = True
            self.content_stack.setCurrentIndex(current_index)
        except Exception:
            if toolbar_swapped or self._right_layout.indexOf(new_toolbar) >= 0:
                self._right_layout.replaceWidget(new_toolbar, old_toolbar)
            for panel in reversed(new_panels):
                if self.content_stack.indexOf(panel) < 0:
                    continue
                try:
                    self.content_stack.removeWidget(panel)
                except Exception:
                    pass
            for index, panel in enumerate(old_panels, start=1):
                if self.content_stack.indexOf(panel) < 0:
                    self.content_stack.insertWidget(index, panel)
            try:
                self.content_stack.setCurrentIndex(current_index)
            except Exception:
                pass
            self._disconnect_publication_signals(new_playlist, new_mix, new_toolbar)
            try:
                new_mix._cleanup_existing_previews()
            except Exception:
                pass
            for widget in prepared:
                widget.deleteLater()
            raise

        self.playlist_panel = new_playlist
        self.mix_tips_panel = new_mix
        self.timeline_panel = new_timeline
        self.analytics_panel = new_analytics
        self.toolbar = new_toolbar
        self.playlist = list(playlist)
        self.quality_metrics = dict(quality_metrics)
        if generation_result is not None:
            self.current_generation_result = generation_result

        try:
            self._disconnect_publication_signals(
                old_panels[0], old_panels[1], old_toolbar
            )
        except Exception as exc:
            self._publication_error_reporter().log_error(
                "transition_view_disconnect", str(exc), {}
            )
        retirement_actions = (
            ("toolbar_hide", old_toolbar.hide),
            ("toolbar_detach", lambda: old_toolbar.setParent(None)),
            ("toolbar_delete", old_toolbar.deleteLater),
            ("playlist_delete", old_panels[0].deleteLater),
            ("timeline_delete", old_panels[2].deleteLater),
            ("analytics_delete", old_panels[3].deleteLater),
        )
        for stage, action in retirement_actions:
            try:
                action()
            except Exception as exc:
                self._publication_error_reporter().log_error(
                    "transition_view_retire", str(exc), {"stage": stage}
                )
        try:
            self._retire_mix_tips_panel(old_panels[1])
        except Exception as exc:
            self._publication_error_reporter().log_error(
                "transition_view_retire", str(exc), {"stage": "mix_tips"}
            )

    def _verteile_uebergaenge(
        self,
        transition_plan,
        bpm_tolerance,
        scoring_context,
        *,
        playlist=None,
        quality_metrics=None,
        generation_result=None,
    ):
        """Publiziert einen Plan per Prepare/Commit ohne destruktiven Rollback."""
        ziel_playlist = list(self.playlist if playlist is None else playlist)
        ziel_quality = dict(self.quality_metrics if quality_metrics is None else quality_metrics)
        prepared = self._prepare_uebergangs_views(
            ziel_playlist, ziel_quality, transition_plan,
            bpm_tolerance, deepcopy(scoring_context),
            generation_result,
        )
        self._commit_uebergangs_views(
            prepared, ziel_playlist, ziel_quality, generation_result
        )

    def _publiziere_generation_result(self, result) -> None:
        """Publiziert genau einen vollstaendigen Result-Zustand atomar."""
        from hpg_core.playlist import legacy_transition_recommendations

        playlist = list(result.tracks)
        quality = result.quality_dict()
        context = result.scoring_context_dict()
        recommendations = legacy_transition_recommendations(result)
        self._verteile_uebergaenge(
            recommendations,
            result.bpm_tolerance,
            context,
            playlist=playlist,
            quality_metrics=quality,
            generation_result=result,
        )
