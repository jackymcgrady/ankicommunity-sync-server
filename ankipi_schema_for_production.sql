--
-- PostgreSQL database dump
--

-- Dumped from database version 14.18 (Homebrew)
-- Dumped by pg_dump version 14.18 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: card_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.card_templates (
    card_template_id integer NOT NULL,
    note_type_id integer NOT NULL,
    name text NOT NULL,
    ordinal integer NOT NULL,
    front_template text,
    back_template text,
    last_sync_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    css text,
    anki_template_id text
);


--
-- Name: card_templates_card_template_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.card_templates_card_template_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: card_templates_card_template_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.card_templates_card_template_id_seq OWNED BY public.card_templates.card_template_id;


--
-- Name: cards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cards (
    card_id bigint,
    deck_id bigint NOT NULL,
    note_id bigint,
    anki_note_id bigint NOT NULL,
    anki_model_id bigint,
    card_ordinal integer,
    front_content text,
    back_content text,
    target_problem text,
    tags text,
    due_number bigint NOT NULL,
    is_leech boolean,
    lapse integer,
    queue integer,
    graduation_date timestamp with time zone,
    created_at timestamp with time zone,
    last_syllabus_run_ts timestamp with time zone,
    anki_card_id bigint,
    last_not_again_ts timestamp with time zone,
    ever_not_again boolean DEFAULT false NOT NULL
);


--
-- Name: cards_card_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cards_card_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cards_card_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cards_card_id_seq OWNED BY public.cards.card_id;


--
-- Name: check_in; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.check_in (
    check_in_id integer NOT NULL,
    module_name text NOT NULL,
    check_in_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_in_module_name_check CHECK ((module_name = ANY (ARRAY['chef'::text, 'waiter'::text])))
);


--
-- Name: check_in_check_in_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.check_in_check_in_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: check_in_check_in_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.check_in_check_in_id_seq OWNED BY public.check_in.check_in_id;


--
-- Name: deck_recipe_prompts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.deck_recipe_prompts (
    deck_recipe_prompt_id integer NOT NULL,
    deck_id integer NOT NULL,
    recipe_prompt_id integer NOT NULL,
    is_selected boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: deck_recipe_prompts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.deck_recipe_prompts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: deck_recipe_prompts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.deck_recipe_prompts_id_seq OWNED BY public.deck_recipe_prompts.deck_recipe_prompt_id;


--
-- Name: deck_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.deck_stats (
    id integer NOT NULL,
    deck_id integer NOT NULL,
    profile_id integer NOT NULL,
    stat_date date NOT NULL,
    reviews_count integer DEFAULT 0,
    time_spent_total_minutes double precision DEFAULT 0.0,
    learning_cards_count_old integer DEFAULT 0,
    mature_cards_count_old integer DEFAULT 0,
    new_cards_seen integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    young_cards_count integer DEFAULT 0,
    mature_cards_count_new integer DEFAULT 0,
    learning_cards_count integer DEFAULT 0,
    mature_cards_count integer DEFAULT 0
);


--
-- Name: deck_stats_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.deck_stats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: deck_stats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.deck_stats_id_seq OWNED BY public.deck_stats.id;


--
-- Name: decks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.decks (
    deck_id integer NOT NULL,
    mother_deck integer NOT NULL,
    profile_id integer NOT NULL,
    name text NOT NULL,
    context text,
    is_active boolean DEFAULT true,
    last_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    last_trophy_date timestamp with time zone,
    trophy_enabled boolean DEFAULT false,
    anki_deck_id bigint,
    syllabus text,
    first_review_ts timestamp with time zone,
    graduated_card_count integer,
    total_time_spent_ms bigint
);


--
-- Name: decks_deck_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.decks_deck_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: decks_deck_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.decks_deck_id_seq OWNED BY public.decks.deck_id;


--
-- Name: leech_helper_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leech_helper_history (
    history_id integer,
    card_id integer NOT NULL,
    helper_pass_id integer NOT NULL,
    created_at timestamp with time zone
);


--
-- Name: leech_helper_history_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.leech_helper_history_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: leech_helper_history_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.leech_helper_history_history_id_seq OWNED BY public.leech_helper_history.history_id;


--
-- Name: note_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_types (
    note_type_id integer NOT NULL,
    profile_id integer NOT NULL,
    anki_model_id bigint NOT NULL,
    name text NOT NULL,
    fields text,
    last_sync_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    ankipi_managed integer DEFAULT 0 NOT NULL,
    ankipi_key text
);


--
-- Name: note_types_note_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_types_note_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_types_note_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_types_note_type_id_seq OWNED BY public.note_types.note_type_id;


--
-- Name: old_problems; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.old_problems (
    id integer,
    target_problem_uuid uuid NOT NULL,
    old_problem_front text NOT NULL,
    old_problem_back text NOT NULL,
    saved_at timestamp with time zone
);


--
-- Name: pass; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pass (
    pass_id bigint,
    profile_id bigint NOT NULL,
    deck_id bigint NOT NULL,
    instruction_type text NOT NULL,
    instruction_data jsonb NOT NULL,
    is_completed boolean,
    created_at timestamp with time zone,
    completed_at timestamp with time zone,
    target_problem text,
    is_leech_helper boolean DEFAULT false NOT NULL,
    card_id integer
);


--
-- Name: pass_pass_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pass_pass_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pass_pass_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pass_pass_id_seq OWNED BY public.pass.pass_id;


--
-- Name: profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profiles (
    profile_id integer,
    name text NOT NULL,
    age_group text,
    personalization text,
    leech_threshold integer,
    timezone text,
    created_at timestamp with time zone,
    anki2_filename text,
    uuid uuid DEFAULT public.uuid_generate_v4(),
    is_active boolean,
    last_waiter_run_utc date,
    waiter_processing boolean DEFAULT false,
    last_chef_run_utc date,
    chef_processing boolean DEFAULT false,
    waiter_pending boolean DEFAULT false,
    chef_pending boolean DEFAULT false
);


--
-- Name: profiles_profile_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.profiles_profile_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: profiles_profile_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.profiles_profile_id_seq OWNED BY public.profiles.profile_id;


--
-- Name: recipe_prompts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipe_prompts (
    recipe_prompt_id integer,
    name text NOT NULL,
    prompt_text text NOT NULL,
    created_at timestamp with time zone,
    description text,
    tags text
);


--
-- Name: card_templates card_template_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.card_templates ALTER COLUMN card_template_id SET DEFAULT nextval('public.card_templates_card_template_id_seq'::regclass);


--
-- Name: cards card_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cards ALTER COLUMN card_id SET DEFAULT nextval('public.cards_card_id_seq'::regclass);


--
-- Name: check_in check_in_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.check_in ALTER COLUMN check_in_id SET DEFAULT nextval('public.check_in_check_in_id_seq'::regclass);


--
-- Name: deck_recipe_prompts deck_recipe_prompt_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deck_recipe_prompts ALTER COLUMN deck_recipe_prompt_id SET DEFAULT nextval('public.deck_recipe_prompts_id_seq'::regclass);


--
-- Name: deck_stats id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deck_stats ALTER COLUMN id SET DEFAULT nextval('public.deck_stats_id_seq'::regclass);


--
-- Name: decks deck_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decks ALTER COLUMN deck_id SET DEFAULT nextval('public.decks_deck_id_seq'::regclass);


--
-- Name: leech_helper_history history_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leech_helper_history ALTER COLUMN history_id SET DEFAULT nextval('public.leech_helper_history_history_id_seq'::regclass);


--
-- Name: note_types note_type_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_types ALTER COLUMN note_type_id SET DEFAULT nextval('public.note_types_note_type_id_seq'::regclass);


--
-- Name: pass pass_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pass ALTER COLUMN pass_id SET DEFAULT nextval('public.pass_pass_id_seq'::regclass);


--
-- Name: profiles profile_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles ALTER COLUMN profile_id SET DEFAULT nextval('public.profiles_profile_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: card_templates card_templates_note_type_id_ordinal_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.card_templates
    ADD CONSTRAINT card_templates_note_type_id_ordinal_key UNIQUE (note_type_id, ordinal);


--
-- Name: card_templates card_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.card_templates
    ADD CONSTRAINT card_templates_pkey PRIMARY KEY (card_template_id);


--
-- Name: check_in check_in_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.check_in
    ADD CONSTRAINT check_in_pkey PRIMARY KEY (check_in_id);


--
-- Name: deck_stats deck_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deck_stats
    ADD CONSTRAINT deck_stats_pkey PRIMARY KEY (id);


--
-- Name: decks decks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decks
    ADD CONSTRAINT decks_pkey PRIMARY KEY (deck_id);


--
-- Name: decks decks_profile_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decks
    ADD CONSTRAINT decks_profile_id_name_key UNIQUE (profile_id, name);


--
-- Name: note_types note_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_types
    ADD CONSTRAINT note_types_pkey PRIMARY KEY (note_type_id);


--
-- Name: note_types note_types_profile_id_anki_model_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_types
    ADD CONSTRAINT note_types_profile_id_anki_model_id_key UNIQUE (profile_id, anki_model_id);


--
-- Name: deck_stats unique_deck_stats_per_day; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deck_stats
    ADD CONSTRAINT unique_deck_stats_per_day UNIQUE (deck_id, stat_date);


--
-- Name: idx_cards_last_not_again; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cards_last_not_again ON public.cards USING btree (deck_id, last_not_again_ts);


--
-- Name: idx_deck_stats_deck_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deck_stats_deck_date ON public.deck_stats USING btree (deck_id, stat_date);


--
-- Name: idx_deck_stats_profile_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deck_stats_profile_date ON public.deck_stats USING btree (profile_id, stat_date);


--
-- Name: idx_decks_graduated_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_decks_graduated_count ON public.decks USING btree (graduated_card_count);


--
-- Name: idx_old_problems_uuid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_old_problems_uuid ON public.old_problems USING btree (target_problem_uuid);


--
-- Name: idx_pass_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pass_card_id ON public.pass USING btree (card_id);


--
-- Name: idx_pass_leech_helper_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pass_leech_helper_pending ON public.pass USING btree (is_completed, is_leech_helper) WHERE (instruction_type = 'create'::text);


--
-- Name: idx_profiles_uuid; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_profiles_uuid ON public.profiles USING btree (uuid);


--
-- Name: unique_note_per_deck; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX unique_note_per_deck ON public.cards USING btree (deck_id, anki_note_id);


--
-- Name: deck_stats update_deck_stats_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_deck_stats_updated_at BEFORE UPDATE ON public.deck_stats FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: card_templates card_templates_note_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.card_templates
    ADD CONSTRAINT card_templates_note_type_id_fkey FOREIGN KEY (note_type_id) REFERENCES public.note_types(note_type_id);


--
-- PostgreSQL database dump complete
--

