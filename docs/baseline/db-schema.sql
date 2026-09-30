--
-- PostgreSQL database dump
--

\restrict rFnZ22SeQtYCumjbKHboEg0gkRSubVpVeprEdNbyazXfEVwZCedLNz7BndjJma8

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: brain_access; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.brain_access (
    brain text NOT NULL,
    org_id text,
    created_by text,
    is_shared boolean DEFAULT false NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: chats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chats (
    id text NOT NULL,
    brain text NOT NULL,
    title text DEFAULT 'Untitled'::text NOT NULL,
    summary text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    updated timestamp with time zone DEFAULT now() NOT NULL,
    org_id text,
    created_by text
);


--
-- Name: connector_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.connector_credentials (
    provider text NOT NULL,
    owner_key text NOT NULL,
    blob text NOT NULL,
    scopes text DEFAULT ''::text NOT NULL,
    expires_at timestamp with time zone,
    status text DEFAULT 'connected'::text NOT NULL,
    updated timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: graph_edge; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.graph_edge (
    source_id character varying NOT NULL,
    target_id character varying NOT NULL,
    relationship_name character varying NOT NULL,
    properties jsonb,
    source_ref_keys character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    source_dataset_ids character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    source_run_ids character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    source_run_refs character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: graph_metadata; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.graph_metadata (
    key character varying NOT NULL,
    value character varying NOT NULL
);


--
-- Name: graph_node; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.graph_node (
    id character varying NOT NULL,
    name character varying,
    type character varying,
    properties jsonb,
    source_ref_keys character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    source_dataset_ids character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    source_run_ids character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    source_run_refs character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: llm_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.llm_calls (
    ts timestamp with time zone DEFAULT now() NOT NULL,
    brain text,
    feature text NOT NULL,
    model text,
    est_prompt_tokens integer,
    est_completion_tokens integer,
    ms integer
);


--
-- Name: slack_workspaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.slack_workspaces (
    owner_key text NOT NULL,
    team_id text NOT NULL,
    team_name text DEFAULT ''::text NOT NULL,
    blob text NOT NULL,
    scopes text DEFAULT ''::text NOT NULL,
    mode text DEFAULT 'read'::text NOT NULL,
    private boolean DEFAULT false NOT NULL,
    bot_user_id text DEFAULT ''::text NOT NULL,
    connected timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: turns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.turns (
    chat_id text NOT NULL,
    idx integer NOT NULL,
    role text NOT NULL,
    text text NOT NULL,
    sources jsonb DEFAULT '[]'::jsonb NOT NULL,
    attachments jsonb DEFAULT '[]'::jsonb NOT NULL,
    at timestamp with time zone
);


--
-- Name: brain_access brain_access_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brain_access
    ADD CONSTRAINT brain_access_pkey PRIMARY KEY (brain);


--
-- Name: chats chats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chats
    ADD CONSTRAINT chats_pkey PRIMARY KEY (id);


--
-- Name: connector_credentials connector_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.connector_credentials
    ADD CONSTRAINT connector_credentials_pkey PRIMARY KEY (provider, owner_key);


--
-- Name: graph_edge graph_edge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.graph_edge
    ADD CONSTRAINT graph_edge_pkey PRIMARY KEY (source_id, target_id, relationship_name);


--
-- Name: graph_metadata graph_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.graph_metadata
    ADD CONSTRAINT graph_metadata_pkey PRIMARY KEY (key);


--
-- Name: graph_node graph_node_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.graph_node
    ADD CONSTRAINT graph_node_pkey PRIMARY KEY (id);


--
-- Name: slack_workspaces slack_workspaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slack_workspaces
    ADD CONSTRAINT slack_workspaces_pkey PRIMARY KEY (owner_key, team_id);


--
-- Name: turns turns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turns
    ADD CONSTRAINT turns_pkey PRIMARY KEY (chat_id, idx);


--
-- Name: chats_brain_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX chats_brain_idx ON public.chats USING btree (brain, updated DESC);


--
-- Name: chats_created_by_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX chats_created_by_idx ON public.chats USING btree (created_by);


--
-- Name: chats_org_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX chats_org_idx ON public.chats USING btree (org_id);


--
-- Name: idx_edge_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edge_source ON public.graph_edge USING btree (source_id);


--
-- Name: idx_edge_source_cover; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edge_source_cover ON public.graph_edge USING btree (source_id) INCLUDE (target_id, relationship_name);


--
-- Name: idx_edge_source_dataset_ids; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edge_source_dataset_ids ON public.graph_edge USING gin (source_dataset_ids);


--
-- Name: idx_edge_source_ref_keys; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edge_source_ref_keys ON public.graph_edge USING gin (source_ref_keys);


--
-- Name: idx_edge_source_run_ids; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edge_source_run_ids ON public.graph_edge USING gin (source_run_ids);


--
-- Name: idx_edge_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edge_target ON public.graph_edge USING btree (target_id);


--
-- Name: idx_edge_target_cover; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_edge_target_cover ON public.graph_edge USING btree (target_id) INCLUDE (source_id, relationship_name);


--
-- Name: idx_node_source_dataset_ids; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_source_dataset_ids ON public.graph_node USING gin (source_dataset_ids);


--
-- Name: idx_node_source_ref_keys; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_source_ref_keys ON public.graph_node USING gin (source_ref_keys);


--
-- Name: idx_node_source_run_ids; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_source_run_ids ON public.graph_node USING gin (source_run_ids);


--
-- Name: idx_node_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_type ON public.graph_node USING btree (type);


--
-- Name: llm_calls_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX llm_calls_ts_idx ON public.llm_calls USING btree (ts);


--
-- Name: graph_edge graph_edge_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.graph_edge
    ADD CONSTRAINT graph_edge_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.graph_node(id) ON DELETE CASCADE;


--
-- Name: graph_edge graph_edge_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.graph_edge
    ADD CONSTRAINT graph_edge_target_id_fkey FOREIGN KEY (target_id) REFERENCES public.graph_node(id) ON DELETE CASCADE;


--
-- Name: turns turns_chat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turns
    ADD CONSTRAINT turns_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES public.chats(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict rFnZ22SeQtYCumjbKHboEg0gkRSubVpVeprEdNbyazXfEVwZCedLNz7BndjJma8

