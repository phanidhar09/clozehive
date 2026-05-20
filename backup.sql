--
-- PostgreSQL database dump
--

\restrict XAHvnPP1ddbIiAB67EVOKNzaXuKF4Nlo4Hk2H3YJgYZbOIj8Loa091QdEskeczC

-- Dumped from database version 16.13 (Debian 16.13-1.pgdg12+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg12+1)

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
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: clozehive
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$;


ALTER FUNCTION public.update_updated_at_column() OWNER TO clozehive;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_requests; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.ai_requests (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    request_type character varying(50) NOT NULL,
    status character varying(30) DEFAULT 'accepted'::character varying NOT NULL,
    input_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    result_payload jsonb,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.ai_requests OWNER TO clozehive;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO clozehive;

--
-- Name: closet_item_embeddings; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.closet_item_embeddings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    closet_item_id uuid NOT NULL,
    content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    embedding public.vector(1536) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.closet_item_embeddings OWNER TO clozehive;

--
-- Name: closet_items; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.closet_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    category character varying(100) NOT NULL,
    color character varying(100),
    fabric character varying(100),
    pattern character varying(100),
    season character varying[],
    occasion character varying[],
    eco_score numeric(3,1),
    tags character varying[],
    image_url text,
    notes text,
    brand character varying(100),
    size character varying(20),
    price numeric(10,2),
    wear_count integer DEFAULT 0 NOT NULL,
    last_worn date,
    is_archived boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    embedding public.vector(1536),
    original_image_url text,
    processed_image_url text,
    background_removed boolean DEFAULT false NOT NULL,
    background_removal_status character varying(20),
    analysis_source character varying(50),
    confidence_score numeric(4,2),
    scan_batch_id character varying(36)
);


ALTER TABLE public.closet_items OWNER TO clozehive;

--
-- Name: follows; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.follows (
    follower_id uuid NOT NULL,
    following_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.follows OWNER TO clozehive;

--
-- Name: group_members; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.group_members (
    group_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying(20) DEFAULT 'member'::character varying NOT NULL,
    joined_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.group_members OWNER TO clozehive;

--
-- Name: groups; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.groups (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    owner_id uuid NOT NULL,
    is_private boolean DEFAULT false NOT NULL,
    invite_code character varying(20) NOT NULL,
    avatar_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.groups OWNER TO clozehive;

--
-- Name: outfits; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.outfits (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name character varying(255),
    occasion character varying(100),
    item_ids character varying[],
    explanation text,
    style_score integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.outfits OWNER TO clozehive;

--
-- Name: packing_plans; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.packing_plans (
    id uuid NOT NULL,
    trip_id uuid NOT NULL,
    user_id uuid NOT NULL,
    take_from_your_closet jsonb DEFAULT '[]'::jsonb NOT NULL,
    you_might_still_need jsonb DEFAULT '[]'::jsonb NOT NULL,
    daily_plan jsonb,
    weather_summary jsonb,
    raw_result jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_saved boolean DEFAULT false NOT NULL
);


ALTER TABLE public.packing_plans OWNER TO clozehive;

--
-- Name: processed_events; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.processed_events (
    event_id uuid NOT NULL,
    topic character varying(100) NOT NULL,
    request_id uuid,
    processed_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.processed_events OWNER TO clozehive;

--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.refresh_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.refresh_tokens OWNER TO clozehive;

--
-- Name: trips; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.trips (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    destination character varying(255) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    purpose character varying(50) NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_saved boolean DEFAULT false NOT NULL
);


ALTER TABLE public.trips OWNER TO clozehive;

--
-- Name: user_credentials; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.user_credentials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    password_hash text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.user_credentials OWNER TO clozehive;

--
-- Name: user_style_profiles; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.user_style_profiles (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    gender character varying(32),
    custom_gender character varying(120),
    height_value numeric(6,2),
    height_unit character varying(8),
    weight_value numeric(7,2),
    weight_unit character varying(8),
    age_range character varying(32),
    body_types jsonb DEFAULT '[]'::jsonb NOT NULL,
    custom_body_type character varying(200),
    fit_preferences jsonb DEFAULT '[]'::jsonb NOT NULL,
    custom_fit_notes character varying(500),
    size_profile jsonb DEFAULT '{}'::jsonb NOT NULL,
    custom_size_notes character varying(500),
    style_preferences jsonb DEFAULT '[]'::jsonb NOT NULL,
    favorite_colors jsonb DEFAULT '[]'::jsonb NOT NULL,
    avoided_colors jsonb DEFAULT '[]'::jsonb NOT NULL,
    neutral_color_preference boolean,
    bold_color_preference boolean,
    occasion_preferences jsonb DEFAULT '[]'::jsonb NOT NULL,
    climate_preferences jsonb DEFAULT '[]'::jsonb NOT NULL,
    onboarding_completed boolean DEFAULT false NOT NULL,
    onboarding_skipped boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    style_summary text
);


ALTER TABLE public.user_style_profiles OWNER TO clozehive;

--
-- Name: users; Type: TABLE; Schema: public; Owner: clozehive
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255) NOT NULL,
    username character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    bio text,
    avatar_url text,
    role character varying(20) DEFAULT 'user'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_verified boolean DEFAULT false NOT NULL,
    google_id character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    body_profile jsonb,
    style_profile jsonb,
    preferences jsonb,
    permissions jsonb,
    avatar_config jsonb,
    auth_provider character varying(20) DEFAULT 'local'::character varying NOT NULL
);


ALTER TABLE public.users OWNER TO clozehive;

--
-- Data for Name: ai_requests; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.ai_requests (id, user_id, request_type, status, input_payload, result_payload, error_message, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.alembic_version (version_num) FROM stdin;
017
\.


--
-- Data for Name: closet_item_embeddings; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.closet_item_embeddings (id, user_id, closet_item_id, content, metadata, embedding, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: closet_items; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.closet_items (id, user_id, name, category, color, fabric, pattern, season, occasion, eco_score, tags, image_url, notes, brand, size, price, wear_count, last_worn, is_archived, created_at, updated_at, embedding, original_image_url, processed_image_url, background_removed, background_removal_status, analysis_source, confidence_score, scan_batch_id) FROM stdin;
d5ffae6d-e016-4cd7-bf8b-7cfd3f069746	98168539-d0b1-41be-bfe0-8174ee2a2cd3	White Soccer Jersey	tops	White	Polyester	Solid	{spring,summer}	{Sport}	\N	\N	/uploads/9fa5a19d-1ca4-4441-b696-cadf47153433.png	A white soccer jersey featuring yellow accents and a prominent logo on the chest. It is branded with 'Fly Better' and sports a sporty design.	Adidas	m	75.00	0	\N	f	2026-05-08 21:05:37.086251+00	2026-05-08 21:05:37.086251+00	\N	/uploads/ceb8ffce-d136-4261-bd6a-d70483a4b482.jpeg	/uploads/9fa5a19d-1ca4-4441-b696-cadf47153433.png	f	skipped	closet_preview_confirm	0.95	ae175856-0370-4fc4-8518-a7f5faf10b04
43b6a45e-dd17-45d0-b3be-2729c45352df	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Grey Champion Hoodie	outerwear	Grey	Cotton	Graphic	{fall,winter}	{Casual,Sport,Travel}	\N	\N	/uploads/190322c8-5e73-4a3c-a572-3c029a66e770.png	A comfortable grey hoodie featuring the Champion logo, perfect for casual wear. It has a front pocket and a hood for added warmth.	Champion	\N	\N	0	\N	f	2026-05-11 18:40:03.107432+00	2026-05-11 18:40:03.107432+00	\N	/uploads/b0dd1251-e01e-414d-a4c4-ae81df00a17a.jpeg	/uploads/190322c8-5e73-4a3c-a572-3c029a66e770.png	f	skipped	closet_preview_confirm	0.98	e4c4f19a-abe7-432c-a0d6-021cb3517405
cdb845d8-0c0c-4480-94e4-ce113885f2f7	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Palm Tree Print Polo Shirt	tops	White	Cotton	Graphic	{spring,summer}	{Casual,Beach,Travel}	\N	\N	/uploads/9ce1ca3c-61e8-4ce3-a184-9d71927b5e11.png	A short-sleeved polo shirt featuring a bold palm tree graphic. Perfect for casual outings, it combines comfort with a tropical style.	\N	\N	\N	0	\N	f	2026-05-11 18:43:02.315681+00	2026-05-11 18:43:02.315681+00	\N	/uploads/4e91a97d-6978-4c7f-aa98-c1834e3c2392.jpg	/uploads/9ce1ca3c-61e8-4ce3-a184-9d71927b5e11.png	t	success_pil	closet_preview_confirm	0.95	bba7a17b-03ba-4c7e-bcc0-fc8d79bf0582
07b05f15-864b-4100-9663-63e1e01b7175	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Black Sunglasses	accessories	Black	Plastic	Solid	{spring,summer,fall}	{Casual,Travel,Beach}	\N	\N	/uploads/7c9111c7-d10f-4cad-b47e-52e560ae435a.png	These are classic black sunglasses with a sleek design. Ideal for protecting your eyes from the sun while adding a touch of style.	\N	\N	\N	0	\N	f	2026-05-11 18:43:02.315681+00	2026-05-11 18:43:02.315681+00	\N	/uploads/4e91a97d-6978-4c7f-aa98-c1834e3c2392.jpg	/uploads/7c9111c7-d10f-4cad-b47e-52e560ae435a.png	t	success_pil	closet_preview_confirm	0.92	bba7a17b-03ba-4c7e-bcc0-fc8d79bf0582
d9580b2b-9bd0-4891-8257-b85357124ffc	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Light Pink Polo Shirt	tops	Pink	Cotton	Solid	{spring,summer,fall}	{Casual,"Business Casual"}	\N	\N	/uploads/8a69be5f-b2df-4ee4-97cf-d69e0407658e.png	A classic light pink polo shirt with a button-up collar. It's suitable for both casual and semi-casual settings with its solid color and simple design.	\N	\N	\N	0	\N	f	2026-05-11 18:44:04.842902+00	2026-05-11 18:44:04.842902+00	\N	/uploads/cca7c273-d11f-4c7e-ab32-1f9b8305b9fd.png	/uploads/8a69be5f-b2df-4ee4-97cf-d69e0407658e.png	t	success_pil	closet_preview_confirm	0.95	976b3bfd-b183-4adf-adee-ff911bec623d
92d3b68e-fa60-409a-a154-46b819c4298f	98168539-d0b1-41be-bfe0-8174ee2a2cd3	White Polo Shirt	tops	white	cotton	solid	{summer,spring,all-season}	{casual,sporty}	\N	\N	/uploads/59552124-e806-46e1-95d2-940054bdc526.png	A white polo shirt with a Puma logo, suitable for casual and sporty occasions.	Puma	\N	\N	0	\N	f	2026-05-12 00:29:54.971816+00	2026-05-12 00:29:54.971816+00	\N	/uploads/05535e12-44c1-4c60-89ca-855867fddeb9.jpg	/uploads/59552124-e806-46e1-95d2-940054bdc526.png	f	skipped_preview_fast	closet_preview_confirm	0.95	e3693923-8155-4b5a-9f2d-db61fdbb64c2
57a51eed-a0de-44ec-b2bc-e36b7e06b58a	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Black Trousers	bottoms	black	unknown	solid	{all-season}	{casual,sports}	\N	\N	/uploads/703684fb-55e8-47c2-81fd-2dac9041d9d3.png	Regular fit black trousers suitable for casual and sports settings.	\N	\N	\N	0	\N	f	2026-05-12 00:29:54.971816+00	2026-05-12 00:29:54.971816+00	\N	/uploads/05535e12-44c1-4c60-89ca-855867fddeb9.jpg	/uploads/703684fb-55e8-47c2-81fd-2dac9041d9d3.png	f	skipped_preview_fast	closet_preview_confirm	0.90	e3693923-8155-4b5a-9f2d-db61fdbb64c2
ec8c8435-f1bf-43d4-8b5d-2e36c5d54d04	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Champion Belt	accessories	black	synthetic	graphic	{all-season}	{party,sporty}	\N	\N	/uploads/3533baf0-71d1-4cc8-9084-57770d72fd1b.png	A championship-style belt with green detailing, adding a sporty touch.	\N	\N	\N	0	\N	f	2026-05-12 00:29:54.971816+00	2026-05-12 00:29:54.971816+00	\N	/uploads/05535e12-44c1-4c60-89ca-855867fddeb9.jpg	/uploads/3533baf0-71d1-4cc8-9084-57770d72fd1b.png	f	skipped_preview_fast	closet_preview_confirm	0.85	e3693923-8155-4b5a-9f2d-db61fdbb64c2
be539971-aad3-4be7-a8c7-dc72d62dc9ed	8941f9fc-3c68-4ee2-a677-0c0a9f266eda	White Polo T-Shirt	tops	white	cotton	solid	{summer,spring,fall}	{casual}	\N	\N	/uploads/9d8cec7e-303c-40e9-8a5b-1f3ef5067150.png	A white polo t-shirt with a Puma logo, suitable for casual occasions.	Puma	\N	\N	0	\N	f	2026-05-12 16:34:07.400995+00	2026-05-12 16:34:07.400995+00	\N	/uploads/2c4b327b-2deb-4898-8805-93ea57a00a48.jpg	/uploads/9d8cec7e-303c-40e9-8a5b-1f3ef5067150.png	f	skipped_preview_fast	closet_preview_confirm	0.97	d898cf21-a8c0-4855-be87-b477ba94ca04
0e58c716-cc7a-416e-8ddb-7bb45d7f2aed	8941f9fc-3c68-4ee2-a677-0c0a9f266eda	Black Trousers	bottoms	black	unknown	solid	{all-season}	{casual}	\N	\N	/uploads/05f60ea0-12e5-4e0a-81e8-68a7f0bfbb37.png	A pair of black trousers, suitable for all seasons.	null	\N	\N	0	\N	f	2026-05-12 16:34:07.400995+00	2026-05-12 16:34:07.400995+00	\N	/uploads/2c4b327b-2deb-4898-8805-93ea57a00a48.jpg	/uploads/05f60ea0-12e5-4e0a-81e8-68a7f0bfbb37.png	f	skipped_preview_fast	closet_preview_confirm	0.94	d898cf21-a8c0-4855-be87-b477ba94ca04
21a23045-4013-4970-b760-4b624308af52	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Gray Champion Hoodie	tops	gray	cotton	graphic	{winter,fall,spring}	{casual,travel}	\N	\N	/uploads/1dc4f0e6-2d61-42f3-a178-fdb7f9732cde.png	A gray Champion hoodie with a front pocket and graphic logo.	Champion	\N	\N	0	\N	f	2026-05-12 19:46:49.882272+00	2026-05-12 19:46:49.882272+00	\N	/uploads/d49397cd-fc8b-4339-aa1f-b31b899bc6a5.jpeg	/uploads/1dc4f0e6-2d61-42f3-a178-fdb7f9732cde.png	f	skipped_preview_fast	closet_preview_confirm	0.98	8d2d683b-b0e5-4113-8604-e2da5e7ffdd3
01269ba4-8c95-43ac-aa31-22c1c336f759	98168539-d0b1-41be-bfe0-8174ee2a2cd3	White Real Madrid Jersey	tops	white	synthetic	graphic	{summer,all-season}	{sporty,casual}	\N	\N	/uploads/ca1b71b6-9f14-476c-83eb-5da33264bebe.png	A white Real Madrid jersey partially visible under the hoodie.	null	\N	\N	0	\N	f	2026-05-12 19:46:49.882272+00	2026-05-12 19:46:49.882272+00	\N	/uploads/d49397cd-fc8b-4339-aa1f-b31b899bc6a5.jpeg	/uploads/ca1b71b6-9f14-476c-83eb-5da33264bebe.png	f	skipped_preview_fast	closet_preview_confirm	0.87	8d2d683b-b0e5-4113-8604-e2da5e7ffdd3
1691e929-6f94-4d0e-b45b-eea20df39c10	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Green Graphic T-Shirt	tops	green	cotton	graphic	{summer,spring,fall}	{casual}	\N	\N	/uploads/ef796d0f-3fcc-4e5b-8298-13e2908650f0.png	Green Abercrombie & Fitch graphic t-shirt with short sleeves, suitable for casual wear.	Abercrombie & Fitch	M	20.00	0	\N	f	2026-05-13 03:32:27.697227+00	2026-05-13 03:32:27.697227+00	\N	/uploads/98e00d22-a4ed-402e-b99d-f79bb30198c0.jpg	/uploads/ef796d0f-3fcc-4e5b-8298-13e2908650f0.png	f	skipped_preview_fast	closet_preview_confirm	0.98	0f884471-2e34-48c0-a793-9e9830a07354
\.


--
-- Data for Name: follows; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.follows (follower_id, following_id, created_at) FROM stdin;
\.


--
-- Data for Name: group_members; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.group_members (group_id, user_id, role, joined_at) FROM stdin;
\.


--
-- Data for Name: groups; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.groups (id, name, description, owner_id, is_private, invite_code, avatar_url, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: outfits; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.outfits (id, user_id, name, occasion, item_ids, explanation, style_score, created_at) FROM stdin;
\.


--
-- Data for Name: packing_plans; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.packing_plans (id, trip_id, user_id, take_from_your_closet, you_might_still_need, daily_plan, weather_summary, raw_result, created_at, updated_at, is_saved) FROM stdin;
cafa96e4-1403-4578-b26d-f7227e5a3376	da2f8660-b447-42a8-8c69-7638668d352b	98168539-d0b1-41be-bfe0-8174ee2a2cd3	[{"name": "White Polo Shirt", "reason": "Suitable for casual outings in warm weather, versatile for various leisure activities.", "item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "category": "tops", "recommended_days": ["Day 1", "Day 4"]}, {"name": "Black Trousers", "reason": "Comfortable and versatile for both casual and semi-casual settings, appropriate for any leisure activity.", "item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "category": "bottoms", "recommended_days": ["Day 1", "Day 3", "Day 5"]}, {"name": "Light Pink Polo Shirt", "reason": "Adds a pop of color, suitable for casual or semi-casual outings in spring/summer weather.", "item_id": "d9580b2b-9bd0-4891-8257-b85357124ffc", "category": "tops", "recommended_days": ["Day 2", "Day 5"]}, {"name": "Black Sunglasses", "reason": "Sleek design for eye protection and style, essential for cloudy days with varying sunlight.", "item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "category": "accessories", "recommended_days": ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6"]}, {"name": "Palm Tree Print Polo Shirt", "reason": "Perfect for a relaxed, tropical vibe during casual and travel days.", "item_id": "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "category": "tops", "recommended_days": ["Day 3", "Day 6"]}, {"name": "Grey Champion Hoodie", "reason": "Useful for cooler evenings or unexpected changes in the weather.", "item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "category": "outerwear", "recommended_days": ["Day 1", "Day 4", "Day 6"]}]	[{"name": "Casual Shorts", "reason": "For comfort and ease during daytime leisure activities in warm weather.", "category": "bottoms"}, {"name": "Comfortable Walking Shoes", "reason": "For leisurely walks and exploring Dallas comfortably.", "category": "footwear"}, {"name": "Light Jacket", "reason": "In case of a drop in temperature during evenings.", "category": "outerwear"}, {"name": "Hat", "reason": "For added sun protection on potentially sunny days.", "category": "accessories"}, {"name": "Swimwear", "reason": "If planning to enjoy any poolside or water-related activities.", "category": "accessories"}]	[{"date": "2026-05-14", "items": ["White Polo Shirt", "Black Trousers", "Black Sunglasses", "Grey Champion Hoodie"], "weather": {"date": "2026-05-14", "temp_low": 20.3, "condition": "Broken Clouds", "temp_high": 30.8, "description": "Broken Clouds, high 31°C / low 20°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175", "43b6a45e-dd17-45d0-b3be-2729c45352df"], "day_label": "Day 1", "outfit_name": "Day 1 outfit"}, {"date": "2026-05-15", "items": ["Light Pink Polo Shirt", "Black Sunglasses"], "weather": {"date": "2026-05-15", "temp_low": 20.9, "condition": "Overcast Clouds", "temp_high": 31.7, "description": "Overcast Clouds, high 32°C / low 21°C."}, "item_ids": ["d9580b2b-9bd0-4891-8257-b85357124ffc", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 2", "outfit_name": "Day 2 outfit"}, {"date": "2026-05-16", "items": ["Black Trousers", "Black Sunglasses", "Palm Tree Print Polo Shirt"], "weather": {"date": "2026-05-16", "temp_low": 22.0, "condition": "Overcast Clouds", "temp_high": 32.0, "description": "Overcast Clouds, high 32°C / low 22°C."}, "item_ids": ["57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175", "cdb845d8-0c0c-4480-94e4-ce113885f2f7"], "day_label": "Day 3", "outfit_name": "Day 3 outfit"}, {"date": "2026-05-17", "items": ["White Polo Shirt", "Black Sunglasses", "Grey Champion Hoodie"], "weather": {"date": "2026-05-17", "temp_low": 31.8, "condition": "Clear Sky", "temp_high": 31.8, "description": "Clear Sky, high 32°C / low 32°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "07b05f15-864b-4100-9663-63e1e01b7175", "43b6a45e-dd17-45d0-b3be-2729c45352df"], "day_label": "Day 4", "outfit_name": "Day 4 outfit"}, {"date": "2026-05-18", "items": ["Black Trousers", "Light Pink Polo Shirt", "Black Sunglasses"], "weather": {"date": "2026-05-18", "temp_low": 12.4, "condition": "Partly Cloudy", "temp_high": 20.7, "description": "Partly Cloudy, high 21°C / low 12°C."}, "item_ids": ["57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "d9580b2b-9bd0-4891-8257-b85357124ffc", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 5", "outfit_name": "Day 5 outfit"}, {"date": "2026-05-19", "items": ["Black Sunglasses", "Palm Tree Print Polo Shirt", "Grey Champion Hoodie"], "weather": {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "description": "Sunny, high 19°C / low 12°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175", "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "43b6a45e-dd17-45d0-b3be-2729c45352df"], "day_label": "Day 6", "outfit_name": "Day 6 outfit"}]	{"days": [{"date": "2026-05-14", "temp_low": 20.3, "condition": "Broken Clouds", "temp_high": 30.8, "description": "Broken Clouds, high 31°C / low 20°C."}, {"date": "2026-05-15", "temp_low": 20.9, "condition": "Overcast Clouds", "temp_high": 31.7, "description": "Overcast Clouds, high 32°C / low 21°C."}, {"date": "2026-05-16", "temp_low": 22.0, "condition": "Overcast Clouds", "temp_high": 32.0, "description": "Overcast Clouds, high 32°C / low 22°C."}, {"date": "2026-05-17", "temp_low": 31.8, "condition": "Clear Sky", "temp_high": 31.8, "description": "Clear Sky, high 32°C / low 32°C."}, {"date": "2026-05-18", "temp_low": 12.4, "condition": "Partly Cloudy", "temp_high": 20.7, "description": "Partly Cloudy, high 21°C / low 12°C."}, {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "description": "Sunny, high 19°C / low 12°C."}], "avg_low": 19.8, "avg_high": 27.7, "rainy_days": 0, "total_days": 6, "recommendation": "Mild conditions; versatile layers should work well.", "dominant_condition": "Overcast Clouds"}	{"items": [{"name": "Underwear", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Socks", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Phone charger", "reason": "Electronics", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "White Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "available_in_closet": true}, {"name": "Light Pink Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "d9580b2b-9bd0-4891-8257-b85357124ffc", "available_in_closet": true}, {"name": "Palm Tree Print Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "available_in_closet": true}, {"name": "Black Trousers", "reason": "From your wardrobe", "category": "bottoms", "quantity": 1, "closet_item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "available_in_closet": true}, {"name": "Grey Champion Hoodie", "reason": "From your wardrobe", "category": "outerwear", "quantity": 1, "closet_item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "available_in_closet": true}], "notes": null, "alerts": ["Missing: shoes"], "purpose": "leisure", "summary": "Packing list for your leisure trip to Dallas, USA. Expect overcast clouds conditions.", "end_date": "2026-05-19", "daily_plan": [{"date": "2026-05-14", "items": ["White Polo Shirt", "Black Trousers", "Black Sunglasses", "Grey Champion Hoodie"], "weather": {"date": "2026-05-14", "temp_low": 20.3, "condition": "Broken Clouds", "temp_high": 30.8, "description": "Broken Clouds, high 31°C / low 20°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175", "43b6a45e-dd17-45d0-b3be-2729c45352df"], "day_label": "Day 1", "outfit_name": "Day 1 outfit"}, {"date": "2026-05-15", "items": ["Light Pink Polo Shirt", "Black Sunglasses"], "weather": {"date": "2026-05-15", "temp_low": 20.9, "condition": "Overcast Clouds", "temp_high": 31.7, "description": "Overcast Clouds, high 32°C / low 21°C."}, "item_ids": ["d9580b2b-9bd0-4891-8257-b85357124ffc", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 2", "outfit_name": "Day 2 outfit"}, {"date": "2026-05-16", "items": ["Black Trousers", "Black Sunglasses", "Palm Tree Print Polo Shirt"], "weather": {"date": "2026-05-16", "temp_low": 22.0, "condition": "Overcast Clouds", "temp_high": 32.0, "description": "Overcast Clouds, high 32°C / low 22°C."}, "item_ids": ["57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175", "cdb845d8-0c0c-4480-94e4-ce113885f2f7"], "day_label": "Day 3", "outfit_name": "Day 3 outfit"}, {"date": "2026-05-17", "items": ["White Polo Shirt", "Black Sunglasses", "Grey Champion Hoodie"], "weather": {"date": "2026-05-17", "temp_low": 31.8, "condition": "Clear Sky", "temp_high": 31.8, "description": "Clear Sky, high 32°C / low 32°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "07b05f15-864b-4100-9663-63e1e01b7175", "43b6a45e-dd17-45d0-b3be-2729c45352df"], "day_label": "Day 4", "outfit_name": "Day 4 outfit"}, {"date": "2026-05-18", "items": ["Black Trousers", "Light Pink Polo Shirt", "Black Sunglasses"], "weather": {"date": "2026-05-18", "temp_low": 12.4, "condition": "Partly Cloudy", "temp_high": 20.7, "description": "Partly Cloudy, high 21°C / low 12°C."}, "item_ids": ["57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "d9580b2b-9bd0-4891-8257-b85357124ffc", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 5", "outfit_name": "Day 5 outfit"}, {"date": "2026-05-19", "items": ["Black Sunglasses", "Palm Tree Print Polo Shirt", "Grey Champion Hoodie"], "weather": {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "description": "Sunny, high 19°C / low 12°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175", "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "43b6a45e-dd17-45d0-b3be-2729c45352df"], "day_label": "Day 6", "outfit_name": "Day 6 outfit"}], "start_date": "2026-05-14", "closet_hint": null, "destination": "Dallas, USA", "packing_list": [{"name": "Underwear", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Socks", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Phone charger", "reason": "Electronics", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "White Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "available_in_closet": true}, {"name": "Light Pink Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "d9580b2b-9bd0-4891-8257-b85357124ffc", "available_in_closet": true}, {"name": "Palm Tree Print Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "available_in_closet": true}, {"name": "Black Trousers", "reason": "From your wardrobe", "category": "bottoms", "quantity": 1, "closet_item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "available_in_closet": true}, {"name": "Grey Champion Hoodie", "reason": "From your wardrobe", "category": "outerwear", "quantity": 1, "closet_item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "available_in_closet": true}], "duration_days": 6, "missing_items": [{"name": "Shoes (not in wardrobe)", "reason": "No shoes found in your closet", "category": "shoes", "quantity": 1, "available_in_closet": false}], "weather_summary": {"days": [{"date": "2026-05-14", "temp_low": 20.3, "condition": "Broken Clouds", "temp_high": 30.8, "description": "Broken Clouds, high 31°C / low 20°C."}, {"date": "2026-05-15", "temp_low": 20.9, "condition": "Overcast Clouds", "temp_high": 31.7, "description": "Overcast Clouds, high 32°C / low 21°C."}, {"date": "2026-05-16", "temp_low": 22.0, "condition": "Overcast Clouds", "temp_high": 32.0, "description": "Overcast Clouds, high 32°C / low 22°C."}, {"date": "2026-05-17", "temp_low": 31.8, "condition": "Clear Sky", "temp_high": 31.8, "description": "Clear Sky, high 32°C / low 32°C."}, {"date": "2026-05-18", "temp_low": 12.4, "condition": "Partly Cloudy", "temp_high": 20.7, "description": "Partly Cloudy, high 21°C / low 12°C."}, {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "description": "Sunny, high 19°C / low 12°C."}], "avg_low": 19.8, "avg_high": 27.7, "rainy_days": 0, "total_days": 6, "recommendation": "Mild conditions; versatile layers should work well.", "dominant_condition": "Overcast Clouds"}, "you_might_still_need": [{"name": "Casual Shorts", "reason": "For comfort and ease during daytime leisure activities in warm weather.", "category": "bottoms"}, {"name": "Comfortable Walking Shoes", "reason": "For leisurely walks and exploring Dallas comfortably.", "category": "footwear"}, {"name": "Light Jacket", "reason": "In case of a drop in temperature during evenings.", "category": "outerwear"}, {"name": "Hat", "reason": "For added sun protection on potentially sunny days.", "category": "accessories"}, {"name": "Swimwear", "reason": "If planning to enjoy any poolside or water-related activities.", "category": "accessories"}], "take_from_your_closet": [{"name": "White Polo Shirt", "reason": "Suitable for casual outings in warm weather, versatile for various leisure activities.", "item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "category": "tops", "recommended_days": ["Day 1", "Day 4"]}, {"name": "Black Trousers", "reason": "Comfortable and versatile for both casual and semi-casual settings, appropriate for any leisure activity.", "item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "category": "bottoms", "recommended_days": ["Day 1", "Day 3", "Day 5"]}, {"name": "Light Pink Polo Shirt", "reason": "Adds a pop of color, suitable for casual or semi-casual outings in spring/summer weather.", "item_id": "d9580b2b-9bd0-4891-8257-b85357124ffc", "category": "tops", "recommended_days": ["Day 2", "Day 5"]}, {"name": "Black Sunglasses", "reason": "Sleek design for eye protection and style, essential for cloudy days with varying sunlight.", "item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "category": "accessories", "recommended_days": ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6"]}, {"name": "Palm Tree Print Polo Shirt", "reason": "Perfect for a relaxed, tropical vibe during casual and travel days.", "item_id": "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "category": "tops", "recommended_days": ["Day 3", "Day 6"]}, {"name": "Grey Champion Hoodie", "reason": "Useful for cooler evenings or unexpected changes in the weather.", "item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "category": "outerwear", "recommended_days": ["Day 1", "Day 4", "Day 6"]}]}	2026-05-12 00:45:03.571328+00	2026-05-12 00:45:03.571335+00	f
3ce3469c-e57a-4114-9e10-79c0bedf3b4d	5b5d58cf-a3c8-43eb-b9af-d284d4c178c8	98168539-d0b1-41be-bfe0-8174ee2a2cd3	[{"name": "White Polo Shirt", "reason": "Light and breathable for the high temperatures; suitable for casual outings.", "item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "category": "tops", "recommended_days": ["Day 1", "Day 2"]}, {"name": "Palm Tree Print Polo Shirt", "reason": "A comfortable and stylish option for leisure activities; matches the summer season.", "item_id": "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "category": "tops", "recommended_days": ["Day 1", "Day 2"]}, {"name": "Black Trousers", "reason": "Versatile and suitable for multiple casual settings; ideal for everyday wear.", "item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "category": "bottoms", "recommended_days": ["Day 1", "Day 2"]}, {"name": "Black Sunglasses", "reason": "Essential for sun protection and adds style on clear, sunny days.", "item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "category": "accessories", "recommended_days": ["Day 1", "Day 2"]}]	[{"name": "Comfortable Walking Shoes", "reason": "For ease and comfort during leisure activities and walking around the city.", "category": "footwear"}, {"name": "Light Jacket", "reason": "For cooler temperatures in the early morning or evening.", "category": "outerwear"}]	[{"date": "2026-05-13", "items": ["White Polo Shirt", "Palm Tree Print Polo Shirt", "Black Trousers", "Black Sunglasses"], "weather": {"date": "2026-05-13", "temp_low": 16.5, "condition": "Clear Sky", "temp_high": 32.0, "data_source": "live", "description": "Clear Sky, high 32°C / low 16°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 1", "outfit_name": "Day 1 — Clear Sky Look", "weather_note": "Hot day (32.0°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-14", "items": ["White Polo Shirt", "Palm Tree Print Polo Shirt", "Black Trousers", "Black Sunglasses"], "weather": {"date": "2026-05-14", "temp_low": 20.9, "condition": "Clear Sky", "temp_high": 32.3, "data_source": "live", "description": "Clear Sky, high 32°C / low 21°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 2", "outfit_name": "Day 2 — Clear Sky Look", "weather_note": "Hot day (32.3°C) — light breathable fabrics, sun hat and sunscreen."}]	{"days": [{"date": "2026-05-13", "temp_low": 16.5, "condition": "Clear Sky", "temp_high": 32.0, "data_source": "live", "description": "Clear Sky, high 32°C / low 16°C."}, {"date": "2026-05-14", "temp_low": 20.9, "condition": "Clear Sky", "temp_high": 32.3, "data_source": "live", "description": "Clear Sky, high 32°C / low 21°C."}], "avg_low": 18.7, "avg_high": 32.1, "rainy_days": 0, "total_days": 2, "data_source": "live", "recommendation": "Prioritise breathable fabrics and sun protection.", "dominant_condition": "Clear Sky"}	{"items": [{"name": "Underwear", "reason": "Daily essential", "category": "essentials", "quantity": 2, "available_in_closet": false}, {"name": "Socks", "reason": "Daily essential", "category": "essentials", "quantity": 2, "available_in_closet": false}, {"name": "Phone charger", "reason": "Electronics", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "White Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "available_in_closet": true}, {"name": "Black Trousers", "reason": "From your wardrobe", "category": "bottoms", "quantity": 1, "closet_item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "available_in_closet": true}, {"name": "Grey Champion Hoodie", "reason": "From your wardrobe", "category": "outerwear", "quantity": 1, "closet_item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "available_in_closet": true}, {"name": "Sunscreen SPF 50+", "reason": "Sun protection", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "Sunglasses", "reason": "Eye protection in strong sun", "category": "accessories", "quantity": 1, "available_in_closet": false}], "notes": null, "alerts": ["Missing: shoes", "Warm weather (32°C) — prioritise light, breathable clothing and sun protection."], "purpose": "leisure", "summary": "Packing list for your leisure trip to Dallas, USA. Expect clear sky conditions (avg 32°C / 19°C). Prioritise breathable fabrics and sun protection.", "end_date": "2026-05-14", "daily_plan": [{"date": "2026-05-13", "items": ["White Polo Shirt", "Palm Tree Print Polo Shirt", "Black Trousers", "Black Sunglasses"], "weather": {"date": "2026-05-13", "temp_low": 16.5, "condition": "Clear Sky", "temp_high": 32.0, "data_source": "live", "description": "Clear Sky, high 32°C / low 16°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 1", "outfit_name": "Day 1 — Clear Sky Look", "weather_note": "Hot day (32.0°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-14", "items": ["White Polo Shirt", "Palm Tree Print Polo Shirt", "Black Trousers", "Black Sunglasses"], "weather": {"date": "2026-05-14", "temp_low": 20.9, "condition": "Clear Sky", "temp_high": 32.3, "data_source": "live", "description": "Clear Sky, high 32°C / low 21°C."}, "item_ids": ["92d3b68e-fa60-409a-a154-46b819c4298f", "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 2", "outfit_name": "Day 2 — Clear Sky Look", "weather_note": "Hot day (32.3°C) — light breathable fabrics, sun hat and sunscreen."}], "start_date": "2026-05-13", "closet_hint": null, "destination": "Dallas, USA", "packing_list": [{"name": "Underwear", "reason": "Daily essential", "category": "essentials", "quantity": 2, "available_in_closet": false}, {"name": "Socks", "reason": "Daily essential", "category": "essentials", "quantity": 2, "available_in_closet": false}, {"name": "Phone charger", "reason": "Electronics", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "White Polo Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "available_in_closet": true}, {"name": "Black Trousers", "reason": "From your wardrobe", "category": "bottoms", "quantity": 1, "closet_item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "available_in_closet": true}, {"name": "Grey Champion Hoodie", "reason": "From your wardrobe", "category": "outerwear", "quantity": 1, "closet_item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "available_in_closet": true}, {"name": "Sunscreen SPF 50+", "reason": "Sun protection", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "Sunglasses", "reason": "Eye protection in strong sun", "category": "accessories", "quantity": 1, "available_in_closet": false}], "duration_days": 2, "missing_items": [{"name": "Shoes (not in wardrobe)", "reason": "No shoes found in your closet", "category": "shoes", "quantity": 1, "available_in_closet": false}], "weather_summary": {"days": [{"date": "2026-05-13", "temp_low": 16.5, "condition": "Clear Sky", "temp_high": 32.0, "data_source": "live", "description": "Clear Sky, high 32°C / low 16°C."}, {"date": "2026-05-14", "temp_low": 20.9, "condition": "Clear Sky", "temp_high": 32.3, "data_source": "live", "description": "Clear Sky, high 32°C / low 21°C."}], "avg_low": 18.7, "avg_high": 32.1, "rainy_days": 0, "total_days": 2, "data_source": "live", "recommendation": "Prioritise breathable fabrics and sun protection.", "dominant_condition": "Clear Sky"}, "weather_forecast": [{"date": "2026-05-13", "temp_low": 16.5, "condition": "Clear Sky", "temp_high": 32.0, "data_source": "live", "description": "Clear Sky, high 32°C / low 16°C."}, {"date": "2026-05-14", "temp_low": 20.9, "condition": "Clear Sky", "temp_high": 32.3, "data_source": "live", "description": "Clear Sky, high 32°C / low 21°C."}], "you_might_still_need": [{"name": "Comfortable Walking Shoes", "reason": "For ease and comfort during leisure activities and walking around the city.", "category": "footwear"}, {"name": "Light Jacket", "reason": "For cooler temperatures in the early morning or evening.", "category": "outerwear"}], "take_from_your_closet": [{"name": "White Polo Shirt", "reason": "Light and breathable for the high temperatures; suitable for casual outings.", "item_id": "92d3b68e-fa60-409a-a154-46b819c4298f", "category": "tops", "recommended_days": ["Day 1", "Day 2"]}, {"name": "Palm Tree Print Polo Shirt", "reason": "A comfortable and stylish option for leisure activities; matches the summer season.", "item_id": "cdb845d8-0c0c-4480-94e4-ce113885f2f7", "category": "tops", "recommended_days": ["Day 1", "Day 2"]}, {"name": "Black Trousers", "reason": "Versatile and suitable for multiple casual settings; ideal for everyday wear.", "item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "category": "bottoms", "recommended_days": ["Day 1", "Day 2"]}, {"name": "Black Sunglasses", "reason": "Essential for sun protection and adds style on clear, sunny days.", "item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "category": "accessories", "recommended_days": ["Day 1", "Day 2"]}]}	2026-05-12 19:31:35.404823+00	2026-05-12 19:31:35.404826+00	f
9900e2fd-e5a7-420e-a9fb-afaa954e6e0d	487da362-5859-41d9-8be5-d99f24385b33	98168539-d0b1-41be-bfe0-8174ee2a2cd3	[{"name": "Black Sunglasses", "reason": "Essential for sunny, hot weather to protect eyes from the sun.", "item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "category": "accessories", "recommended_days": ["Day 2", "Day 4", "Day 5"]}]	[{"name": "Light, breathable dress shirts", "reason": "Needed for formal occasions during hot weather, providing comfort and professionalism.", "category": "tops"}, {"name": "Lightweight formal trousers", "reason": "Suitable for formal occasions in hot weather, ensuring comfort while maintaining a professional look.", "category": "bottoms"}, {"name": "Breathable dress shoes", "reason": "To provide comfort during formal events in hot weather.", "category": "footwear"}, {"name": "Light jacket", "reason": "A jacket is needed for Day 6, as the temperature drops significantly.", "category": "outerwear"}]	[{"date": "2026-05-14", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-14", "temp_low": 33.5, "condition": "Overcast Clouds", "temp_high": 44.7, "data_source": "live", "description": "Overcast Clouds, high 45°C / low 34°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 1", "outfit_name": "Day 1 — Overcast Clouds Look", "weather_note": "Hot day (44.7°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-15", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-15", "temp_low": 34.3, "condition": "Clear Sky", "temp_high": 44.9, "data_source": "live", "description": "Clear Sky, high 45°C / low 34°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 2", "outfit_name": "Day 2 — Clear Sky Look", "weather_note": "Hot day (44.9°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-16", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-16", "temp_low": 35.1, "condition": "Scattered Clouds", "temp_high": 44.5, "data_source": "live", "description": "Scattered Clouds, high 44°C / low 35°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 3", "outfit_name": "Day 3 — Scattered Clouds Look", "weather_note": "Hot day (44.5°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-17", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-17", "temp_low": 35.2, "condition": "Clear Sky", "temp_high": 45.5, "data_source": "live", "description": "Clear Sky, high 46°C / low 35°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 4", "outfit_name": "Day 4 — Clear Sky Look", "weather_note": "Hot day (45.5°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-18", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-18", "temp_low": 37.1, "condition": "Clear Sky", "temp_high": 39.0, "data_source": "live", "description": "Clear Sky, high 39°C / low 37°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 5", "outfit_name": "Day 5 — Clear Sky Look", "weather_note": "Hot day (39.0°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-19", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "data_source": "static_profile", "description": "Sunny, high 19°C / low 12°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 6", "outfit_name": "Day 6 — Sunny Look", "weather_note": "Mild conditions (19.3°C) — versatile layers work well."}]	{"days": [{"date": "2026-05-14", "temp_low": 33.5, "condition": "Overcast Clouds", "temp_high": 44.7, "data_source": "live", "description": "Overcast Clouds, high 45°C / low 34°C."}, {"date": "2026-05-15", "temp_low": 34.3, "condition": "Clear Sky", "temp_high": 44.9, "data_source": "live", "description": "Clear Sky, high 45°C / low 34°C."}, {"date": "2026-05-16", "temp_low": 35.1, "condition": "Scattered Clouds", "temp_high": 44.5, "data_source": "live", "description": "Scattered Clouds, high 44°C / low 35°C."}, {"date": "2026-05-17", "temp_low": 35.2, "condition": "Clear Sky", "temp_high": 45.5, "data_source": "live", "description": "Clear Sky, high 46°C / low 35°C."}, {"date": "2026-05-18", "temp_low": 37.1, "condition": "Clear Sky", "temp_high": 39.0, "data_source": "live", "description": "Clear Sky, high 39°C / low 37°C."}, {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "data_source": "static_profile", "description": "Sunny, high 19°C / low 12°C."}], "avg_low": 31.1, "avg_high": 39.6, "rainy_days": 0, "total_days": 6, "data_source": "partial", "recommendation": "Prioritise breathable fabrics and sun protection.", "dominant_condition": "Clear Sky"}	{"items": [{"name": "Underwear", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Socks", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Phone charger", "reason": "Electronics", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "Green Graphic T-Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "1691e929-6f94-4d0e-b45b-eea20df39c10", "available_in_closet": true}, {"name": "Gray Champion Hoodie", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "21a23045-4013-4970-b760-4b624308af52", "available_in_closet": true}, {"name": "White Real Madrid Jersey", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "01269ba4-8c95-43ac-aa31-22c1c336f759", "available_in_closet": true}, {"name": "Black Trousers", "reason": "From your wardrobe", "category": "bottoms", "quantity": 1, "closet_item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "available_in_closet": true}, {"name": "Grey Champion Hoodie", "reason": "From your wardrobe", "category": "outerwear", "quantity": 1, "closet_item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "available_in_closet": true}, {"name": "Champion Belt", "reason": "From your wardrobe", "category": "accessories", "quantity": 1, "closet_item_id": "ec8c8435-f1bf-43d4-8b5d-2e36c5d54d04", "available_in_closet": true}, {"name": "Black Sunglasses", "reason": "From your wardrobe", "category": "accessories", "quantity": 1, "closet_item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "available_in_closet": true}, {"name": "Sunscreen SPF 50+", "reason": "Sun protection", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "Sunglasses", "reason": "Eye protection in strong sun", "category": "accessories", "quantity": 1, "available_in_closet": false}], "notes": null, "alerts": ["Missing: shoes", "Extreme heat expected (40°C) — pack breathable fabrics and stay hydrated."], "purpose": "formal", "summary": "Packing list for your formal trip to Delhi, India. Expect clear sky conditions (avg 40°C / 31°C). Prioritise breathable fabrics and sun protection.", "end_date": "2026-05-19", "daily_plan": [{"date": "2026-05-14", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-14", "temp_low": 33.5, "condition": "Overcast Clouds", "temp_high": 44.7, "data_source": "live", "description": "Overcast Clouds, high 45°C / low 34°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 1", "outfit_name": "Day 1 — Overcast Clouds Look", "weather_note": "Hot day (44.7°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-15", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-15", "temp_low": 34.3, "condition": "Clear Sky", "temp_high": 44.9, "data_source": "live", "description": "Clear Sky, high 45°C / low 34°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 2", "outfit_name": "Day 2 — Clear Sky Look", "weather_note": "Hot day (44.9°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-16", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-16", "temp_low": 35.1, "condition": "Scattered Clouds", "temp_high": 44.5, "data_source": "live", "description": "Scattered Clouds, high 44°C / low 35°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 3", "outfit_name": "Day 3 — Scattered Clouds Look", "weather_note": "Hot day (44.5°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-17", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-17", "temp_low": 35.2, "condition": "Clear Sky", "temp_high": 45.5, "data_source": "live", "description": "Clear Sky, high 46°C / low 35°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 4", "outfit_name": "Day 4 — Clear Sky Look", "weather_note": "Hot day (45.5°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-18", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-18", "temp_low": 37.1, "condition": "Clear Sky", "temp_high": 39.0, "data_source": "live", "description": "Clear Sky, high 39°C / low 37°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 5", "outfit_name": "Day 5 — Clear Sky Look", "weather_note": "Hot day (39.0°C) — light breathable fabrics, sun hat and sunscreen."}, {"date": "2026-05-19", "items": ["Black Sunglasses"], "weather": {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "data_source": "static_profile", "description": "Sunny, high 19°C / low 12°C."}, "item_ids": ["07b05f15-864b-4100-9663-63e1e01b7175"], "day_label": "Day 6", "outfit_name": "Day 6 — Sunny Look", "weather_note": "Mild conditions (19.3°C) — versatile layers work well."}], "start_date": "2026-05-14", "closet_hint": null, "destination": "Delhi, India", "packing_list": [{"name": "Underwear", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Socks", "reason": "Daily essential", "category": "essentials", "quantity": 6, "available_in_closet": false}, {"name": "Phone charger", "reason": "Electronics", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "Green Graphic T-Shirt", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "1691e929-6f94-4d0e-b45b-eea20df39c10", "available_in_closet": true}, {"name": "Gray Champion Hoodie", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "21a23045-4013-4970-b760-4b624308af52", "available_in_closet": true}, {"name": "White Real Madrid Jersey", "reason": "From your wardrobe", "category": "tops", "quantity": 1, "closet_item_id": "01269ba4-8c95-43ac-aa31-22c1c336f759", "available_in_closet": true}, {"name": "Black Trousers", "reason": "From your wardrobe", "category": "bottoms", "quantity": 1, "closet_item_id": "57a51eed-a0de-44ec-b2bc-e36b7e06b58a", "available_in_closet": true}, {"name": "Grey Champion Hoodie", "reason": "From your wardrobe", "category": "outerwear", "quantity": 1, "closet_item_id": "43b6a45e-dd17-45d0-b3be-2729c45352df", "available_in_closet": true}, {"name": "Champion Belt", "reason": "From your wardrobe", "category": "accessories", "quantity": 1, "closet_item_id": "ec8c8435-f1bf-43d4-8b5d-2e36c5d54d04", "available_in_closet": true}, {"name": "Black Sunglasses", "reason": "From your wardrobe", "category": "accessories", "quantity": 1, "closet_item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "available_in_closet": true}, {"name": "Sunscreen SPF 50+", "reason": "Sun protection", "category": "essentials", "quantity": 1, "available_in_closet": false}, {"name": "Sunglasses", "reason": "Eye protection in strong sun", "category": "accessories", "quantity": 1, "available_in_closet": false}], "duration_days": 6, "missing_items": [{"name": "Shoes (not in wardrobe)", "reason": "No shoes found in your closet", "category": "shoes", "quantity": 1, "available_in_closet": false}], "weather_summary": {"days": [{"date": "2026-05-14", "temp_low": 33.5, "condition": "Overcast Clouds", "temp_high": 44.7, "data_source": "live", "description": "Overcast Clouds, high 45°C / low 34°C."}, {"date": "2026-05-15", "temp_low": 34.3, "condition": "Clear Sky", "temp_high": 44.9, "data_source": "live", "description": "Clear Sky, high 45°C / low 34°C."}, {"date": "2026-05-16", "temp_low": 35.1, "condition": "Scattered Clouds", "temp_high": 44.5, "data_source": "live", "description": "Scattered Clouds, high 44°C / low 35°C."}, {"date": "2026-05-17", "temp_low": 35.2, "condition": "Clear Sky", "temp_high": 45.5, "data_source": "live", "description": "Clear Sky, high 46°C / low 35°C."}, {"date": "2026-05-18", "temp_low": 37.1, "condition": "Clear Sky", "temp_high": 39.0, "data_source": "live", "description": "Clear Sky, high 39°C / low 37°C."}, {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "data_source": "static_profile", "description": "Sunny, high 19°C / low 12°C."}], "avg_low": 31.1, "avg_high": 39.6, "rainy_days": 0, "total_days": 6, "data_source": "partial", "recommendation": "Prioritise breathable fabrics and sun protection.", "dominant_condition": "Clear Sky"}, "weather_forecast": [{"date": "2026-05-14", "temp_low": 33.5, "condition": "Overcast Clouds", "temp_high": 44.7, "data_source": "live", "description": "Overcast Clouds, high 45°C / low 34°C."}, {"date": "2026-05-15", "temp_low": 34.3, "condition": "Clear Sky", "temp_high": 44.9, "data_source": "live", "description": "Clear Sky, high 45°C / low 34°C."}, {"date": "2026-05-16", "temp_low": 35.1, "condition": "Scattered Clouds", "temp_high": 44.5, "data_source": "live", "description": "Scattered Clouds, high 44°C / low 35°C."}, {"date": "2026-05-17", "temp_low": 35.2, "condition": "Clear Sky", "temp_high": 45.5, "data_source": "live", "description": "Clear Sky, high 46°C / low 35°C."}, {"date": "2026-05-18", "temp_low": 37.1, "condition": "Clear Sky", "temp_high": 39.0, "data_source": "live", "description": "Clear Sky, high 39°C / low 37°C."}, {"date": "2026-05-19", "temp_low": 11.6, "condition": "Sunny", "temp_high": 19.3, "data_source": "static_profile", "description": "Sunny, high 19°C / low 12°C."}], "you_might_still_need": [{"name": "Light, breathable dress shirts", "reason": "Needed for formal occasions during hot weather, providing comfort and professionalism.", "category": "tops"}, {"name": "Lightweight formal trousers", "reason": "Suitable for formal occasions in hot weather, ensuring comfort while maintaining a professional look.", "category": "bottoms"}, {"name": "Breathable dress shoes", "reason": "To provide comfort during formal events in hot weather.", "category": "footwear"}, {"name": "Light jacket", "reason": "A jacket is needed for Day 6, as the temperature drops significantly.", "category": "outerwear"}], "take_from_your_closet": [{"name": "Black Sunglasses", "reason": "Essential for sunny, hot weather to protect eyes from the sun.", "item_id": "07b05f15-864b-4100-9663-63e1e01b7175", "category": "accessories", "recommended_days": ["Day 2", "Day 4", "Day 5"]}]}	2026-05-13 03:36:14.920106+00	2026-05-13 03:36:14.92012+00	f
\.


--
-- Data for Name: processed_events; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.processed_events (event_id, topic, request_id, processed_at) FROM stdin;
\.


--
-- Data for Name: refresh_tokens; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.refresh_tokens (id, user_id, token_hash, expires_at, revoked, created_at) FROM stdin;
1a970317-bb52-4c55-941f-3368f351fede	98168539-d0b1-41be-bfe0-8174ee2a2cd3	43fc886f244bb29e045e3c470a356a065c913199162e8966c966c12999355682	2026-05-15 21:02:53.251784+00	t	2026-05-08 21:02:53.246213+00
1dbba0a2-617b-4172-af72-3445f072d9f3	98168539-d0b1-41be-bfe0-8174ee2a2cd3	7260f1ffd85e9a15f466ba23ed8d4207b2e06d4b550d13f18447e589489a2850	2026-05-15 21:18:49.357777+00	t	2026-05-08 21:18:49.232573+00
3ebcc90e-1146-412f-bb62-a5758048004e	98168539-d0b1-41be-bfe0-8174ee2a2cd3	7af2efa2c3765c1e5a053e26759d6513c6bd5931896534433c8d34fff14a68af	2026-05-17 11:11:46.829831+00	t	2026-05-10 11:11:46.685082+00
7a4d055e-90e8-495a-995b-22a9d0844476	98168539-d0b1-41be-bfe0-8174ee2a2cd3	1abdc0c44c0674ca5c78396f92fe5cc5f3d1cf28b7e790572f09398505e47def	2026-05-18 18:36:49.418619+00	t	2026-05-11 18:36:49.361022+00
d74ba1ff-2e02-4578-8a50-4a64f3151f5f	98168539-d0b1-41be-bfe0-8174ee2a2cd3	a6b64e9d7a68b4b7571c912c2f45ae624935e3d775384b813f978a2380949968	2026-05-18 19:18:47.557534+00	t	2026-05-11 19:18:47.470751+00
53bdfda0-7945-4e97-b6ff-fb5bf6f6e86c	98168539-d0b1-41be-bfe0-8174ee2a2cd3	f1d677304e9e5bdcfa727f9a8bff587b53f30f61bdeef7932a86b33c44c24924	2026-05-18 20:14:41.996092+00	f	2026-05-11 20:14:41.898656+00
9a0b977f-a77a-4c3e-8750-11e97a6a5a36	98168539-d0b1-41be-bfe0-8174ee2a2cd3	fa17033a20f57b77d83b8bdf632315f15d1436f71fe96dacddae948118f92fcb	2026-05-18 20:29:46.450286+00	f	2026-05-11 20:29:46.404009+00
dc9e06d3-037e-42ef-8665-7a39f8af916a	98168539-d0b1-41be-bfe0-8174ee2a2cd3	705ce04d25727c599dbdfa393cea4a479fdba77af179b9801097a7b24d685a61	2026-05-18 21:04:40.214614+00	f	2026-05-11 21:04:40.12881+00
fa420c7b-7450-4b4f-bcfd-1e6f04ac1c85	98168539-d0b1-41be-bfe0-8174ee2a2cd3	db4f816fc8894619b38617a83e0d9baea4a146310e403f82293d2c255754df3f	2026-05-18 21:19:14.065038+00	f	2026-05-11 21:19:13.990232+00
01c5ca2e-0fbb-434d-a300-4f38512cc1fc	98168539-d0b1-41be-bfe0-8174ee2a2cd3	49a2d79c39cb7621a17c53ffab3ff8fe4465b2ed1bf355628df0143b75a32c6a	2026-05-18 21:19:43.625615+00	f	2026-05-11 21:19:43.621042+00
d1a197f5-03fb-4e3f-9a2a-d3982b998759	03ee9c93-2946-4701-866b-ebd80835e709	a151c4c9cb9a9ea0ddde0533534134070461d5ea8936c1a47a6dd643f6f31647	2026-05-18 21:20:11.125091+00	f	2026-05-11 21:20:10.945593+00
b54940cf-76f2-4b85-ac02-f6072263c420	98168539-d0b1-41be-bfe0-8174ee2a2cd3	e9930463b8624e4112e1308bc6656034f151cfc91756ba7796545ae8819845b4	2026-05-18 21:23:51.066475+00	f	2026-05-11 21:23:51.035491+00
a1a71ae5-41f9-429a-98db-e3f5d203b26e	98168539-d0b1-41be-bfe0-8174ee2a2cd3	f86d73c0f2206898750f5270b80f249aaa2f702ca3ff8addcc0a088f86fc0598	2026-05-18 21:24:34.988989+00	f	2026-05-11 21:24:34.972749+00
6c394652-0d94-431f-913a-d56440302ae5	98168539-d0b1-41be-bfe0-8174ee2a2cd3	6ecffb9e776e5a36f0db44e7c57e183bcd7a41d32f3019601ec1cdb0ea737966	2026-05-18 21:33:56.645553+00	f	2026-05-11 21:33:56.607194+00
a37acd38-b118-46a1-b605-7db254c6a486	20ea039d-a5c6-49e6-899b-d4e08e57634f	3ac3d399f0410e503572f4a377166799bfa8238d7562eed0b3fb4f6105f15c40	2026-05-18 21:34:32.966258+00	f	2026-05-11 21:34:32.866104+00
01fac95d-26ad-422e-ac8b-44b0e27d373d	98168539-d0b1-41be-bfe0-8174ee2a2cd3	3e0b6c74e17fc1cc3e5c4d2e9e29a8f1d247859c01e35859b5cfe0700885d8c1	2026-05-18 21:45:28.454288+00	f	2026-05-11 21:45:28.43148+00
79275dca-629c-4cf3-9183-119d6a7f7ef5	3aaba8af-04d3-4b6f-b69f-820e7ead0893	329185404d850f8ac3feb98363a77568cabf462c3a9b107576a759804c3b5e3b	2026-05-18 21:52:29.798314+00	f	2026-05-11 21:52:29.30088+00
3175901e-2528-46cb-8d12-36ff7327b2b5	3aaba8af-04d3-4b6f-b69f-820e7ead0893	eac544ca2d6c32e483a0c1d4a13f36f1f9d09615f2b2c95a91ffa305a5d2cb84	2026-05-18 21:52:35.761743+00	f	2026-05-11 21:52:35.509764+00
2309b80b-f935-4b8f-b7c7-74d8ca82c3a3	69e633a0-1c2f-4f73-bfa1-bff2a60419c6	74565625a693ea2be965605ba45cfb6fc908032ad48fb3811f592a1a18f4ccb7	2026-05-18 21:52:45.322098+00	f	2026-05-11 21:52:45.055017+00
1cc992bf-aa53-4096-9477-ad536338af2b	3aaba8af-04d3-4b6f-b69f-820e7ead0893	ea77d87fd6dae4f998f679735a1d0964d0aeda6e01959f1af07b19630d119a73	2026-05-18 21:52:45.683635+00	f	2026-05-11 21:52:45.388538+00
5f66694b-ab36-4e91-b804-dc9811d7a6ab	8941f9fc-3c68-4ee2-a677-0c0a9f266eda	5d2831eae4c658c9be46695a7d500accb4f9dacac0f2b6b4f21799252cdeb78f	2026-05-18 21:55:20.421354+00	f	2026-05-11 21:55:20.396434+00
de54eac7-2861-4880-9fe3-983b8939678e	98168539-d0b1-41be-bfe0-8174ee2a2cd3	2963b00e9ef2efb87450dc3d0ca4d2f87c382e25d8d93fca02b780588fa47d4c	2026-05-18 22:04:41.402394+00	f	2026-05-11 22:04:41.360069+00
ae1b6e70-acd4-4067-8461-ffaad2925d04	f2bff438-1ef6-4429-813e-7e9c13ae6208	9628915bfb7a4e7ba30165fd2c335f32db8cad759a4b07c3de481accdbe8fe31	2026-05-18 22:07:33.756496+00	f	2026-05-11 22:07:33.464091+00
ea21a18f-3484-4738-b443-b45742152490	98168539-d0b1-41be-bfe0-8174ee2a2cd3	dda46346d0da562737cc121347bbbefbfb63cfb68aa467e65fe41993725d85d7	2026-05-18 22:13:32.090955+00	f	2026-05-11 22:13:32.01545+00
f8c9e840-de30-4f1d-9189-9cb5d093ae04	98168539-d0b1-41be-bfe0-8174ee2a2cd3	0f1f4751db365a0e79d9f675bca7453f741165468e2c9104bbd4273444d25d73	2026-05-18 22:25:40.882864+00	f	2026-05-11 22:25:40.824539+00
ab439a47-3365-489d-bd78-0a44a9feaac4	98168539-d0b1-41be-bfe0-8174ee2a2cd3	2f5033cf1d86a09c47dba977ad8864302f718f95d45ee9e095e27df4eb0290b6	2026-05-18 22:28:15.912113+00	f	2026-05-11 22:28:15.867381+00
813f2bd1-11b1-491c-ab00-d591fbd1d705	8941f9fc-3c68-4ee2-a677-0c0a9f266eda	c9107f55a8d5dde3bb7d484825670b06133c3b04f03fe260780d8f59ccf1cccd	2026-05-18 22:31:26.050839+00	f	2026-05-11 22:31:26.011544+00
4f328199-80bb-4280-ab11-3a6ee4217a9b	98168539-d0b1-41be-bfe0-8174ee2a2cd3	7c10ff745615baa0c7d6e1229a824da12cb27b715cf34f1f592caf813070eb26	2026-05-18 22:49:29.477705+00	t	2026-05-11 22:49:29.393337+00
8c19f542-87d5-4c9b-b9c1-82a818a08533	98168539-d0b1-41be-bfe0-8174ee2a2cd3	aa378778c4e6c59be70c3499bba93260bee198db651f476a37f017eb8720c790	2026-05-18 23:10:18.813391+00	t	2026-05-11 23:10:18.649123+00
d98a5484-4766-4a60-ae81-f40f45d544b1	98168539-d0b1-41be-bfe0-8174ee2a2cd3	47dcd34175993d4d6212e28949445bf5719f58cc7e9619ce41c3cb6f1f95bf0b	2026-05-19 00:25:35.631404+00	t	2026-05-12 00:25:35.543828+00
61ee6e23-7046-46ec-ac85-2b21582502ea	98168539-d0b1-41be-bfe0-8174ee2a2cd3	de632af1b06c12a5c8fc5813d8c304b25d6db5b833c4d1a83568dfabfbc05359	2026-05-18 22:42:02.937175+00	t	2026-05-11 22:42:02.722945+00
18ac7bb0-fceb-4914-b00b-c9f625bcc630	98168539-d0b1-41be-bfe0-8174ee2a2cd3	b7605dfb56dadb607ff89b076e292d6b554af05e093cb8fdf179a5b0e6dc0bfa	2026-05-19 01:35:24.126816+00	t	2026-05-12 01:35:23.936524+00
d09170b4-001f-4164-82d7-3cd555ebdada	98168539-d0b1-41be-bfe0-8174ee2a2cd3	aaffa86eb0f0e6cc06822ef92eb86f2a0c624e888ae29b2abbfefbfc404f0ab6	2026-05-19 16:17:13.313084+00	t	2026-05-12 16:17:13.100698+00
edfb6a8e-704d-458d-9b51-7df0a024cc22	8941f9fc-3c68-4ee2-a677-0c0a9f266eda	3238478abc18722889796f654e2c5776b3bfa9da6261d560551625017da4a109	2026-05-19 16:31:34.858085+00	t	2026-05-12 16:31:34.838216+00
4c1fa46d-0c84-46a4-a1f9-d267f5822673	98168539-d0b1-41be-bfe0-8174ee2a2cd3	99faf08e43fd075b4f7702b843def84a029c65165e2c4e5ccb3c2ae47efd383a	2026-05-19 16:34:34.098345+00	t	2026-05-12 16:34:34.092532+00
c9f248c4-e060-45c6-82ad-976bc9997848	98168539-d0b1-41be-bfe0-8174ee2a2cd3	54cbfedf0787a9d5e8f8505427a7cf317471125183074de9704ad2e0b49f9f30	2026-05-19 00:44:44.627322+00	t	2026-05-12 00:44:44.5577+00
8dbdb511-edb5-4942-8f19-a09908223633	98168539-d0b1-41be-bfe0-8174ee2a2cd3	b4dfaafa48d704b4266c13bb05122d3205bea47c34a1fb579949e38bea357057	2026-05-19 18:49:14.758984+00	t	2026-05-12 18:49:14.669835+00
d2d3a5ae-7e68-4976-b949-e58746f66b24	98168539-d0b1-41be-bfe0-8174ee2a2cd3	0f7f82ca1bd0b19759cfb250b35271e30fbff873bb0674974ec12a82f45dccec	2026-05-19 18:48:33.541812+00	t	2026-05-12 18:48:33.448678+00
a2e2c584-7157-44bb-8266-9dd9fb412c09	98168539-d0b1-41be-bfe0-8174ee2a2cd3	090116f91c80e97986d60735a549746fdc5058b70acdfe67f8d51ec5108b7f20	2026-05-19 18:49:16.693537+00	t	2026-05-12 18:49:16.484344+00
3e81032e-36ab-4dab-a119-ae79106667de	98168539-d0b1-41be-bfe0-8174ee2a2cd3	183c2f9edfe9e0059e1f1011e6167d4c48c5870cc090426f10e47f5f9c211f6d	2026-05-19 19:30:49.276547+00	t	2026-05-12 19:30:49.24039+00
53bfe9d1-4ed0-477d-bd99-61790afe87a7	98168539-d0b1-41be-bfe0-8174ee2a2cd3	32f5a5df5acf1c04b0aacb4e014c698cac14ea01b2268874246202c7128fa9d8	2026-05-19 19:33:36.67163+00	t	2026-05-12 19:33:36.657491+00
ce54c658-1c72-4c0f-afe2-9e96bb8dfd6e	98168539-d0b1-41be-bfe0-8174ee2a2cd3	23797a33778ea5e4ddf821e532343a5b64c17e544cc20c92d63f20d2cd24b512	2026-05-19 19:27:07.778684+00	t	2026-05-12 19:27:07.625472+00
287927ca-8245-4075-b745-64b2ec85736f	98168539-d0b1-41be-bfe0-8174ee2a2cd3	b86d9e133669a640bc18f5870f6d2c0055323856961dfd652e716d553c6edbee	2026-05-19 22:06:05.739887+00	t	2026-05-12 22:06:05.333025+00
f1786c57-a26a-4544-971e-712858965cb1	98168539-d0b1-41be-bfe0-8174ee2a2cd3	eb2477b7cf6b81a626e7f24dd458f385acf9dd59961717531bdd0eade92f8c2a	2026-05-19 22:06:06.563309+00	f	2026-05-12 22:06:06.491763+00
89699217-7737-46b4-8d21-f4a62c6bcaa6	98168539-d0b1-41be-bfe0-8174ee2a2cd3	c13b6da2d0fc4ce466d02ee1816019265ae228c05e360ddabbf630f64c699984	2026-05-19 21:31:48.946878+00	t	2026-05-12 21:31:48.693961+00
508d6072-d51a-44bb-b280-85edf4a1fc65	98168539-d0b1-41be-bfe0-8174ee2a2cd3	97027ac1364d526d564155f38c98131705794f980cf636d4d6af8a51343b43f6	2026-05-19 23:35:33.005246+00	t	2026-05-12 23:35:32.809783+00
ef1170df-65c3-4d80-beac-55450b950bb7	98168539-d0b1-41be-bfe0-8174ee2a2cd3	beefadeeaa75f9ff1e0d22d441254a4c841f4683a617e80d340aeee5ea24a274	2026-05-20 03:28:15.004491+00	t	2026-05-13 03:28:14.788228+00
4889c446-8438-4980-9696-61ec5f2435d5	98168539-d0b1-41be-bfe0-8174ee2a2cd3	667befc5c45823004df021cf1b96c0a1e17d3aacf4bec3598c8bca0f66dee718	2026-05-20 03:30:41.479797+00	t	2026-05-13 03:30:41.325304+00
20d9557b-8fff-40d1-b39c-90683d663b6e	20ea039d-a5c6-49e6-899b-d4e08e57634f	71b8f769b5629c28559d412bdce6929e4e7b1cefabbc5d68dc11b4c1168d4a73	2026-05-20 03:38:25.936768+00	t	2026-05-13 03:38:25.908782+00
c84ac568-b570-4cff-8f78-7c1197dfceb2	98168539-d0b1-41be-bfe0-8174ee2a2cd3	cbdb9108bae7def6c2e97d662173a42eaf3770cb10595c15c8a3fe8fe8fb9a5b	2026-05-20 03:40:26.672385+00	f	2026-05-13 03:40:26.664557+00
\.


--
-- Data for Name: trips; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.trips (id, user_id, destination, start_date, end_date, purpose, notes, created_at, updated_at, is_saved) FROM stdin;
da2f8660-b447-42a8-8c69-7638668d352b	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Dallas, USA	2026-05-14	2026-05-19	leisure	\N	2026-05-12 00:44:56.965371+00	2026-05-12 00:44:56.965377+00	f
5b5d58cf-a3c8-43eb-b9af-d284d4c178c8	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Dallas, USA	2026-05-13	2026-05-14	leisure	\N	2026-05-12 19:31:29.346281+00	2026-05-12 19:31:29.346284+00	f
487da362-5859-41d9-8be5-d99f24385b33	98168539-d0b1-41be-bfe0-8174ee2a2cd3	Delhi, India	2026-05-14	2026-05-19	formal	\N	2026-05-13 03:36:07.801904+00	2026-05-13 03:36:07.801907+00	f
\.


--
-- Data for Name: user_credentials; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.user_credentials (id, user_id, password_hash, created_at, updated_at) FROM stdin;
de50330a-c1bb-479a-ae7d-a1519bf6efd6	98168539-d0b1-41be-bfe0-8174ee2a2cd3	\N	2026-05-08 21:02:46.108599+00	2026-05-08 21:02:46.108599+00
8b0a3aeb-754c-4b99-bc29-803e47639a42	03ee9c93-2946-4701-866b-ebd80835e709	\N	2026-05-11 21:20:10.945593+00	2026-05-11 21:20:10.945593+00
77988d9d-92dc-4909-b4bf-defa3fdbf27a	20ea039d-a5c6-49e6-899b-d4e08e57634f	\N	2026-05-11 21:34:32.866104+00	2026-05-11 21:34:32.866104+00
42430215-0b2c-4c80-862c-a4311db4f411	3aaba8af-04d3-4b6f-b69f-820e7ead0893	$2b$12$J/pcXMbhv2z2qdjcWh6Xce7Uu0cbogCcUTC09d9tEYwoUTdUunBCa	2026-05-11 21:52:29.30088+00	2026-05-11 21:52:29.30088+00
fbe62836-6faf-4708-9a52-50bb1bb8a184	69e633a0-1c2f-4f73-bfa1-bff2a60419c6	$2b$12$0lirBNVel/eVctECyxrkTuIJWCQd5oLWBHzxy3yLID1QNlKzNBCJO	2026-05-11 21:52:45.055017+00	2026-05-11 21:52:45.055017+00
8b0011ff-751a-4a91-bfaf-caa8a4f8b1de	8941f9fc-3c68-4ee2-a677-0c0a9f266eda	\N	2026-05-11 21:55:20.396434+00	2026-05-11 21:55:20.396434+00
6af7c729-76c5-4058-b5da-4dfab67d9dc3	f2bff438-1ef6-4429-813e-7e9c13ae6208	$2b$12$gBkj8s9/ZXsLz3AyAnxoWeBbNnhZC.0XoNrTOEc9mYDn1EP3Lm0IO	2026-05-11 22:07:33.464091+00	2026-05-11 22:07:33.464091+00
\.


--
-- Data for Name: user_style_profiles; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.user_style_profiles (id, user_id, gender, custom_gender, height_value, height_unit, weight_value, weight_unit, age_range, body_types, custom_body_type, fit_preferences, custom_fit_notes, size_profile, custom_size_notes, style_preferences, favorite_colors, avoided_colors, neutral_color_preference, bold_color_preference, occasion_preferences, climate_preferences, onboarding_completed, onboarding_skipped, created_at, updated_at, style_summary) FROM stdin;
bb84a8c7-85d8-4752-834d-6fdfd2624825	03ee9c93-2946-4701-866b-ebd80835e709	\N	\N	\N	\N	\N	\N	\N	[]	\N	[]	\N	{}	\N	[]	[]	[]	\N	\N	[]	[]	f	f	2026-05-11 21:20:10.945593+00	2026-05-11 21:20:10.945593+00	\N
2cd6234f-776b-48a2-b065-311fc4ab63e3	3aaba8af-04d3-4b6f-b69f-820e7ead0893	\N	\N	\N	\N	\N	\N	\N	[]	\N	[]	\N	{}	\N	[]	[]	[]	\N	\N	[]	[]	f	f	2026-05-11 21:52:29.30088+00	2026-05-11 21:52:29.30088+00	\N
f8cbfd3a-e12c-40b7-b4e6-1981f683bafd	69e633a0-1c2f-4f73-bfa1-bff2a60419c6	\N	\N	\N	\N	\N	\N	\N	[]	\N	[]	\N	{}	\N	[]	[]	[]	\N	\N	[]	[]	f	f	2026-05-11 21:52:45.055017+00	2026-05-11 21:52:45.055017+00	\N
d47b2cac-2947-4651-9fee-5ff025c20b98	f2bff438-1ef6-4429-813e-7e9c13ae6208	\N	\N	\N	\N	\N	\N	\N	[]	\N	[]	\N	{}	\N	[]	[]	[]	\N	\N	[]	[]	f	f	2026-05-11 22:07:33.464091+00	2026-05-11 22:07:33.464091+00	\N
6f0923cb-7285-4d48-bd95-dc75e195fd23	20ea039d-a5c6-49e6-899b-d4e08e57634f	male	\N	\N	\N	\N	\N	\N	[]	\N	[]	\N	{}	\N	[]	[]	[]	\N	\N	[]	[]	t	t	2026-05-11 21:34:32.866104+00	2026-05-13 03:39:30.395346+00	The user is a male with a preference for a tailored fit that flatters their athletic build, favoring structured silhouettes that enhance their physique. They gravitate towards a versatile color palette of earthy tones and muted shades, suitable for both professional settings and casual outings. Given their active lifestyle, they require breathable fabrics that are comfortable in a moderate climate, allowing for easy transitions between various occasions.
f45bc31c-a412-4229-b2a4-ed943d0eacdb	98168539-d0b1-41be-bfe0-8174ee2a2cd3	male	\N	\N	\N	\N	\N	\N	[]	\N	[]	\N	{}	\N	[]	[]	[]	\N	\N	[]	[]	t	f	2026-05-11 21:22:21.281969+00	2026-05-12 00:34:00.46971+00	\N
a2d494e2-7037-4057-9748-a6346c4c7422	8941f9fc-3c68-4ee2-a677-0c0a9f266eda	male	\N	\N	\N	\N	\N	25_34	["Athletic", "Average"]	\N	["Regular fit", "Relaxed fit", "Athletic fit"]	\N	{"tops_size": "M", "shirt_size": "M", "waist_size": "32", "tshirt_size": "M", "bottoms_size": "32"}	\N	["Casual", "Business casual", "Formal", "Streetwear", "Trendy", "Luxury", "Sporty", "Classic", "Travel-friendly", "Traditional", "Comfort-first"]	[]	[]	\N	\N	[]	[]	t	f	2026-05-11 21:55:20.396434+00	2026-05-12 16:32:48.21176+00	\N
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: clozehive
--

COPY public.users (id, email, username, name, bio, avatar_url, role, is_active, is_verified, google_id, created_at, updated_at, body_profile, style_profile, preferences, permissions, avatar_config, auth_provider) FROM stdin;
98168539-d0b1-41be-bfe0-8174ee2a2cd3	phanidharreddy93@gmail.com	phanidhar_reddy	Phanidhar Reddy	\N	https://lh3.googleusercontent.com/a/ACg8ocLJq_2z7U3n-0Gs-5O1cWR71YkWNth-iv9ejRkGWVrjJVX-AQ=s96-c	user	t	t	117673689522427344717	2026-05-08 21:02:46.108599+00	2026-05-11 21:45:02.058289+00	\N	\N	\N	\N	\N	google
03ee9c93-2946-4701-866b-ebd80835e709	rphanidhar99@gmail.com	phanidhar_r	Phanidhar R	\N	https://lh3.googleusercontent.com/a/ACg8ocKLj1RbeEHT2Wr3e3U3BFyjXreacHFAxcTb7IiHQY07wYdXcA=s96-c	user	t	t	116227170258332528239	2026-05-11 21:20:10.945593+00	2026-05-11 21:45:02.058289+00	\N	\N	\N	\N	\N	google
3aaba8af-04d3-4b6f-b69f-820e7ead0893	smoke_authprov@test.com	smokeauthprov	Test Smoke	\N	\N	user	t	f	\N	2026-05-11 21:52:29.30088+00	2026-05-11 21:52:36.028882+00	\N	\N	\N	\N	\N	local
69e633a0-1c2f-4f73-bfa1-bff2a60419c6	userb_conflict@test.com	conflictb	User B	\N	\N	user	t	f	\N	2026-05-11 21:52:45.055017+00	2026-05-11 21:52:45.055017+00	\N	\N	\N	\N	\N	local
8941f9fc-3c68-4ee2-a677-0c0a9f266eda	reddyreplies@gmail.com	phanidhar_reddy2	Phanidhar Reddy	\N	https://lh3.googleusercontent.com/a/ACg8ocLkl75he6lw9j5afzlSjR2CgfHMBnifSEDhRYIYqeBVP5qnow=s96-c	user	t	t	101234380649261016012	2026-05-11 21:55:20.396434+00	2026-05-11 21:55:20.396434+00	\N	\N	\N	\N	\N	google
f2bff438-1ef6-4429-813e-7e9c13ae6208	user@example.com	string	phani	\N	\N	user	t	f	\N	2026-05-11 22:07:33.464091+00	2026-05-11 22:07:33.464091+00	\N	\N	\N	\N	\N	local
20ea039d-a5c6-49e6-899b-d4e08e57634f	phanidharreddy979@gmail.com	phanidhar_reddy1	Phanidhar Reddy	\N	https://lh3.googleusercontent.com/a/ACg8ocIcJSJVNed-ekkWvXQeeQk8u6QyaU7zIquVgdzrnhWi7D7ESg=s96-c	user	t	t	110617549684055320947	2026-05-11 21:34:32.866104+00	2026-05-13 03:40:02.960507+00	\N	\N	\N	{"calendar": false, "location": false, "timezone": null, "location_label": null, "location_coords": null}	\N	google
\.


--
-- Name: ai_requests ai_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.ai_requests
    ADD CONSTRAINT ai_requests_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: closet_item_embeddings closet_item_embeddings_closet_item_id_key; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.closet_item_embeddings
    ADD CONSTRAINT closet_item_embeddings_closet_item_id_key UNIQUE (closet_item_id);


--
-- Name: closet_item_embeddings closet_item_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.closet_item_embeddings
    ADD CONSTRAINT closet_item_embeddings_pkey PRIMARY KEY (id);


--
-- Name: closet_items closet_items_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.closet_items
    ADD CONSTRAINT closet_items_pkey PRIMARY KEY (id);


--
-- Name: follows follows_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.follows
    ADD CONSTRAINT follows_pkey PRIMARY KEY (follower_id, following_id);


--
-- Name: group_members group_members_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.group_members
    ADD CONSTRAINT group_members_pkey PRIMARY KEY (group_id, user_id);


--
-- Name: groups groups_invite_code_key; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_invite_code_key UNIQUE (invite_code);


--
-- Name: groups groups_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_pkey PRIMARY KEY (id);


--
-- Name: outfits outfits_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.outfits
    ADD CONSTRAINT outfits_pkey PRIMARY KEY (id);


--
-- Name: packing_plans packing_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.packing_plans
    ADD CONSTRAINT packing_plans_pkey PRIMARY KEY (id);


--
-- Name: processed_events processed_events_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.processed_events
    ADD CONSTRAINT processed_events_pkey PRIMARY KEY (event_id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: trips trips_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.trips
    ADD CONSTRAINT trips_pkey PRIMARY KEY (id);


--
-- Name: packing_plans uq_packing_plans_trip_user; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.packing_plans
    ADD CONSTRAINT uq_packing_plans_trip_user UNIQUE (trip_id, user_id);


--
-- Name: user_credentials user_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.user_credentials
    ADD CONSTRAINT user_credentials_pkey PRIMARY KEY (id);


--
-- Name: user_credentials user_credentials_user_id_key; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.user_credentials
    ADD CONSTRAINT user_credentials_user_id_key UNIQUE (user_id);


--
-- Name: user_style_profiles user_style_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.user_style_profiles
    ADD CONSTRAINT user_style_profiles_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_google_id_key; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_google_id_key UNIQUE (google_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_ai_requests_type_created; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_ai_requests_type_created ON public.ai_requests USING btree (request_type, created_at);


--
-- Name: idx_ai_requests_user_status; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_ai_requests_user_status ON public.ai_requests USING btree (user_id, status);


--
-- Name: idx_closet_item_embeddings_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_closet_item_embeddings_user_id ON public.closet_item_embeddings USING btree (user_id);


--
-- Name: idx_closet_item_embeddings_vector; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_closet_item_embeddings_vector ON public.closet_item_embeddings USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: idx_closet_items_category; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_closet_items_category ON public.closet_items USING btree (category);


--
-- Name: idx_closet_items_scan_batch_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_closet_items_scan_batch_id ON public.closet_items USING btree (scan_batch_id);


--
-- Name: idx_closet_items_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_closet_items_user_id ON public.closet_items USING btree (user_id);


--
-- Name: idx_follows_follower_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_follows_follower_id ON public.follows USING btree (follower_id);


--
-- Name: idx_follows_following_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_follows_following_id ON public.follows USING btree (following_id);


--
-- Name: idx_group_members_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_group_members_user_id ON public.group_members USING btree (user_id);


--
-- Name: idx_groups_owner_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_groups_owner_id ON public.groups USING btree (owner_id);


--
-- Name: idx_outfits_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_outfits_user_id ON public.outfits USING btree (user_id);


--
-- Name: idx_refresh_tokens_token_hash; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_refresh_tokens_token_hash ON public.refresh_tokens USING btree (token_hash);


--
-- Name: idx_refresh_tokens_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_refresh_tokens_user_id ON public.refresh_tokens USING btree (user_id);


--
-- Name: idx_trips_destination; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_trips_destination ON public.trips USING btree (destination);


--
-- Name: idx_trips_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_trips_user_id ON public.trips USING btree (user_id);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_name_trgm; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_users_name_trgm ON public.users USING gin (name public.gin_trgm_ops);


--
-- Name: idx_users_username; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_users_username ON public.users USING btree (username);


--
-- Name: idx_users_username_trgm; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX idx_users_username_trgm ON public.users USING gin (username public.gin_trgm_ops);


--
-- Name: ix_closet_items_category; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_closet_items_category ON public.closet_items USING btree (category);


--
-- Name: ix_closet_items_created_at; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_closet_items_created_at ON public.closet_items USING btree (created_at);


--
-- Name: ix_closet_items_embedding_hnsw; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_closet_items_embedding_hnsw ON public.closet_items USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: ix_closet_items_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_closet_items_user_id ON public.closet_items USING btree (user_id);


--
-- Name: ix_outfits_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_outfits_user_id ON public.outfits USING btree (user_id);


--
-- Name: ix_packing_plans_trip_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_packing_plans_trip_id ON public.packing_plans USING btree (trip_id);


--
-- Name: ix_packing_plans_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_packing_plans_user_id ON public.packing_plans USING btree (user_id);


--
-- Name: ix_trips_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE INDEX ix_trips_user_id ON public.trips USING btree (user_id);


--
-- Name: ix_user_style_profiles_user_id; Type: INDEX; Schema: public; Owner: clozehive
--

CREATE UNIQUE INDEX ix_user_style_profiles_user_id ON public.user_style_profiles USING btree (user_id);


--
-- Name: closet_items set_updated_at; Type: TRIGGER; Schema: public; Owner: clozehive
--

CREATE TRIGGER set_updated_at BEFORE UPDATE ON public.closet_items FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: groups set_updated_at; Type: TRIGGER; Schema: public; Owner: clozehive
--

CREATE TRIGGER set_updated_at BEFORE UPDATE ON public.groups FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: trips set_updated_at; Type: TRIGGER; Schema: public; Owner: clozehive
--

CREATE TRIGGER set_updated_at BEFORE UPDATE ON public.trips FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: users set_updated_at; Type: TRIGGER; Schema: public; Owner: clozehive
--

CREATE TRIGGER set_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: ai_requests ai_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.ai_requests
    ADD CONSTRAINT ai_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: closet_item_embeddings closet_item_embeddings_closet_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.closet_item_embeddings
    ADD CONSTRAINT closet_item_embeddings_closet_item_id_fkey FOREIGN KEY (closet_item_id) REFERENCES public.closet_items(id) ON DELETE CASCADE;


--
-- Name: closet_item_embeddings closet_item_embeddings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.closet_item_embeddings
    ADD CONSTRAINT closet_item_embeddings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: closet_items closet_items_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.closet_items
    ADD CONSTRAINT closet_items_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: follows follows_follower_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.follows
    ADD CONSTRAINT follows_follower_id_fkey FOREIGN KEY (follower_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: follows follows_following_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.follows
    ADD CONSTRAINT follows_following_id_fkey FOREIGN KEY (following_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: group_members group_members_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.group_members
    ADD CONSTRAINT group_members_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id) ON DELETE CASCADE;


--
-- Name: group_members group_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.group_members
    ADD CONSTRAINT group_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: groups groups_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: outfits outfits_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.outfits
    ADD CONSTRAINT outfits_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: packing_plans packing_plans_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.packing_plans
    ADD CONSTRAINT packing_plans_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id) ON DELETE CASCADE;


--
-- Name: packing_plans packing_plans_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.packing_plans
    ADD CONSTRAINT packing_plans_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: trips trips_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.trips
    ADD CONSTRAINT trips_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_credentials user_credentials_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.user_credentials
    ADD CONSTRAINT user_credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_style_profiles user_style_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: clozehive
--

ALTER TABLE ONLY public.user_style_profiles
    ADD CONSTRAINT user_style_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict XAHvnPP1ddbIiAB67EVOKNzaXuKF4Nlo4Hk2H3YJgYZbOIj8Loa091QdEskeczC

