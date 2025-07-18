from core.group.stat.smain import *
from core.group.stat.config import ProfileConfig
from core.group.stat.manager import *
from group_stat import *

class ProfileManager:
    def __init__(self):
        logger.info("ProfileManager instance initialized.")
        self._conn = None
        self.font_cache = {}

    async def connect(self):
        logger.debug("Attempting to connect to profiles database asynchronously.")
        if self._conn is not None:
            logger.warning("Profiles database connection already exists, skipping reconnection.")
            return
        try:
            self._conn = await aiosqlite.connect('profiles.db')
            logger.info("Profiles database connected asynchronously.")
            await self._init_db_async()
            logger.info("Asynchronous profiles database schema check/initialization completed.")
        except Exception as e:
            logger.exception("Failed to establish profiles database connection or initialize schema asynchronously:")
            raise

    async def close(self):
        logger.debug("Attempting to close profiles database connection.")
        if self._conn is not None:
            try:
                await self._conn.close()
                self._conn = None
                logger.info("Profiles database connection closed successfully.")
            except Exception as e:
                logger.exception("Error occurred while closing profiles database connection:")
        else:
            logger.info("Profiles database connection was already closed or not established.")

    async def _init_db_async(self):
        logger.debug("Starting asynchronous profiles database schema initialization.")
        if self._conn is None:
            logger.error("Cannot perform async DB init: connection is None. Aborting.")
            return
        cursor = await self._conn.cursor()
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        await cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            hp INTEGER DEFAULT 100 CHECK(hp >= 0 AND hp <= 150),
            level INTEGER DEFAULT 1 CHECK(level >= 1 AND level <= 169),
            exp INTEGER DEFAULT 0,
            lumcoins INTEGER DEFAULT 0,
            daily_messages INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            flames INTEGER DEFAULT 0,
            last_work_time REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        await cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
        await self._conn.commit()
        logger.info("Asynchronous profiles database tables checked/created.")

    async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
        logger.debug(f"Fetching or creating profile for user_id: {user.id}")
        if self._conn is None:
            logger.error("Database connection is not established when trying to get user profile.")
            raise RuntimeError("Database connection is not established.")
        
        cursor = await self._conn.cursor()
        await cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name
        ''', (user.id, user.username, user.first_name, user.last_name))
        await self._conn.commit()
        logger.debug(f"User {user.id} information updated/inserted in 'profiles.db users' table.")
        
        user_id = user.id
        await cursor.execute('''
        INSERT OR IGNORE INTO user_profiles (user_id)
        VALUES (?)
        ''', (user_id,))
        await self._conn.commit()
        logger.debug(f"User profile for {user_id} ensured existence in 'profiles.db user_profiles' table.")

        await cursor.execute('''
        SELECT * FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        profile = await cursor.fetchone()

        if not profile:
            logger.error(f"Profile not found for user_id {user.id} after creation attempt in profiles.db. This should not happen.")
            return None

        columns = [column[0] for column in cursor.description]
        profile_data = dict(zip(columns, profile))
        logger.debug(f"Profile data retrieved for user_id {user.id} from profiles.db.")
        
        profile_data['display_name'] = f"@{user.username}" if user.username else user.full_name 
        logger.debug(f"Display name set to: {profile_data['display_name']} for user {user.id}.")
        
        rp_stats = await get_user_rp_stats(user_id)
        if rp_stats:
            profile_data['hp'] = rp_stats.get('hp', ProfileConfig.MAX_HP)
            logger.debug(f"HP fetched from database.py: {profile_data['hp']} for user {user.id}.")
        else:
            profile_data['hp'] = ProfileConfig.MAX_HP
            logger.warning(f"Could not retrieve HP from database.py for user {user.id}, defaulting to {ProfileConfig.MAX_HP}.")


        logger.info(f"Successfully retrieved/created profile for user {user.id}.")
        return profile_data

    async def record_message(self, user: types.User) -> None:
        logger.debug(f"Recording message activity for user_id: {user.id}.")
        if self._conn is None:
            logger.error("Database connection is not established when trying to record message.")
            raise RuntimeError("Database connection is not established.")
        
        cursor = await self._conn.cursor()
        await cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name
        ''', (user.id, user.username, user.first_name, user.last_name))
        await self._conn.commit()
        logger.debug(f"User {user.id} information updated/inserted in 'profiles.db users' table for message recording.")

        user_id = user.id
        await cursor.execute('''
        INSERT OR IGNORE INTO user_profiles (user_id)
        VALUES (?)
        ''', (user_id,))
        await self._conn.commit()
        logger.debug(f"User profile for {user_id} ensured existence in 'user_profiles' table for message recording.")

        await cursor.execute('''
        SELECT total_messages, level, exp, lumcoins
        FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        profile_data = await cursor.fetchone()

        if not profile_data:
            logger.error(f"Profile not found for user_id: {user_id} in record_message. Skipping message count.")
            return

        total_messages, level, exp, lumcoins = profile_data
        old_total_messages = total_messages
        total_messages += 1
        logger.debug(f"User {user_id}: Total messages updated from {old_total_messages} to {total_messages}.")
        
        exp_added = 0
        if total_messages > 0 and total_messages % ProfileConfig.EXP_PER_MESSAGE_INTERVAL == 0:
            exp_added = ProfileConfig.EXP_AMOUNT_PER_INTERVAL
            logger.debug(f"User {user_id}: {exp_added} EXP added due to message interval.")
        
        new_exp = exp + exp_added
        new_level = level
        new_lumcoins = lumcoins
        logger.debug(f"User {user_id}: Current EXP: {exp}, New EXP: {new_exp}, Current Level: {level}, Current Lumcoins: {lumcoins}.")

        while new_exp >= self._get_exp_for_level(new_level) and new_level < ProfileConfig.MAX_LEVEL:
            needed_for_current = self._get_exp_for_level(new_level)
            new_exp -= needed_for_current
            new_level += 1
            coins_this_level = self._get_lumcoins_for_level(new_level)
            new_lumcoins += coins_this_level
            logger.info(f"User {user_id} leveled up to {new_level}! Earned {coins_this_level} Lumcoins. Remaining EXP: {new_exp}.")

        await cursor.execute('''
        UPDATE user_profiles
        SET daily_messages = daily_messages + 1,
            total_messages = ?,
            exp = ?,
            level = ?,
            lumcoins = ?
        WHERE user_id = ?
        ''', (total_messages, new_exp, new_level, new_lumcoins, user_id))
        await self._conn.commit()
        logger.info(f"User {user_id} profile updated: Total messages: {total_messages}, Level: {new_level}, EXP: {new_exp}, Lumcoins: {new_lumcoins}.")

    def _get_exp_for_level(self, level: int) -> int:
        logger.debug(f"Calculating required EXP for level {level}.")
        if level < 1:
            logger.warning(f"Invalid level {level} provided for EXP calculation, returning 0.")
            return 0
        base_exp = 100
        coefficient = 2
        multiplier = 5
        required_exp = base_exp + (level ** coefficient) * multiplier
        logger.debug(f"Required EXP for level {level}: {required_exp}.")
        return required_exp

    def _get_lumcoins_for_level(self, level: int) -> int:
        logger.debug(f"Determining Lumcoins reward for level {level}.")
        for lvl, coins in sorted(ProfileConfig.LUMCOINS_PER_LEVEL.items(), reverse=True):
            if level >= lvl:
                logger.debug(f"Lumcoins for level {level}: {coins} (from level {lvl} threshold).")
                return coins
        logger.debug(f"No specific Lumcoins reward found for level {level}, returning default 1.")
        return 1

    async def generate_profile_image(self, user: types.User, profile: Dict[str, Any], bot_instance: Bot) -> BytesIO:
        logger.info(f"Starting profile image generation for user {user.id}.")
        font_xlarge, font_large, font_medium, font_small = None, None, None, None
        try:
            if ProfileConfig.FONT_PATH not in self.font_cache:
                if os.path.exists(ProfileConfig.FONT_PATH):
                    self.font_cache[ProfileConfig.FONT_PATH] = {
                            'xlarge': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_XLARGE, encoding="UTF-8"),
                            'large': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_LARGE, encoding="UTF-8"),
                            'medium': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_MEDIUM, encoding="UTF-8"),
                            'small': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_SMALL, encoding="UTF-8")
                    }
                    logger.info(f"Font '{ProfileConfig.FONT_PATH}' loaded successfully and cached.")
                else:
                    logger.error(f"Font file not found: {ProfileConfig.FONT_PATH}. Raising FileNotFoundError.")
                    raise FileNotFoundError(f"Font file not found: {ProfileConfig.FONT_PATH}")
            
            font_xlarge = self.font_cache[ProfileConfig.FONT_PATH]['xlarge']
            font_large = self.font_cache[ProfileConfig.FONT_PATH]['large']
            font_medium = self.font_cache[ProfileConfig.FONT_PATH]['medium']
            font_small = self.font_cache[ProfileConfig.FONT_PATH]['small']
            logger.debug("Fonts retrieved from cache.")

        except (FileNotFoundError, OSError, Exception) as e:
            logger.error(f"Failed to load custom font '{ProfileConfig.FONT_PATH}': {e}. Using default Pillow font.", exc_info=True)
            font_xlarge = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_XLARGE + 4)
            font_large = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_LARGE + 4)
            font_medium = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_MEDIUM + 4)
            font_small = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_SMALL + 4)
            logger.info("Default Pillow fonts loaded.")

        base_image = Image.new('RGBA', (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), (0, 0, 0, 0))
        draw_base = ImageDraw.Draw(base_image)
        logger.debug("Base image and draw object created for the card.")

        shadow_offset_x = 5
        shadow_offset_y = 5
        shadow_color = (0, 0, 0, 100)
        draw_base.rounded_rectangle(
            (shadow_offset_x, shadow_offset_y, ProfileConfig.CARD_WIDTH + shadow_offset_x, ProfileConfig.CARD_HEIGHT + shadow_offset_y),
            radius=ProfileConfig.CARD_RADIUS,
            fill=shadow_color
        )
        logger.debug("Card shadow drawn.")

        background_image = None
        try:
            logger.debug(f"Background Loading: Step 1 - Attempting to load background from local path: {ProfileConfig.DEFAULT_LOCAL_BG_PATH}.")
            if not os.path.exists(ProfileConfig.DEFAULT_LOCAL_BG_PATH):
                raise FileNotFoundError(f"Local background file not found: {ProfileConfig.DEFAULT_LOCAL_BG_PATH}")
            
            background_image = Image.open(ProfileConfig.DEFAULT_LOCAL_BG_PATH).convert("RGBA")
            logger.debug("Background Loading: Step 2 - Local background image opened with PIL and converted to RGBA.")
            
            bg_width, bg_height = background_image.size
            card_aspect = ProfileConfig.CARD_WIDTH / ProfileConfig.CARD_HEIGHT
            bg_aspect = bg_width / bg_height

            if card_aspect > bg_aspect:
                new_bg_height = ProfileConfig.CARD_HEIGHT
                new_bg_width = int(bg_width * (new_bg_height / bg_height))
            else:
                new_bg_width = ProfileConfig.CARD_WIDTH
                new_bg_height = int(bg_height * (new_bg_width / bg_width))
            
            background_image = background_image.resize((new_bg_width, new_bg_height), Image.Resampling.LANCZOS)
            logger.debug(f"Background Loading: Step 3 - Background image resized to {new_bg_width}x{new_bg_height}.")

            left = (new_bg_width - ProfileConfig.CARD_WIDTH) / 2
            top = (new_bg_height - ProfileConfig.CARD_HEIGHT) / 2
            right = (new_bg_width + ProfileConfig.CARD_WIDTH) / 2
            bottom = (new_bg_height + ProfileConfig.CARD_HEIGHT) / 2
            background_image = background_image.crop((left, top, right, bottom))
            logger.debug("Background Loading: Step 4 - Background image cropped to fit card dimensions.")

            mask_bg = Image.new('L', (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), 0)
            mask_bg_draw = ImageDraw.Draw(mask_bg)
            mask_bg_draw.rounded_rectangle(
                (0, 0, ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT),
                radius=ProfileConfig.CARD_RADIUS,
                fill=255
            )
            background_image.putalpha(mask_bg)
            logger.info("Background Loading: Step 5 - Rounded corner mask applied to background image.")

        except FileNotFoundError as e:
            logger.error(f"Background Loading: Failed to load local background: {e}. Using solid color fallback.", exc_info=True)
            background_image = Image.new('RGBA', (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), (50, 50, 70, 255))
            mask_bg = Image.new('L', (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), 0)
            mask_bg_draw = ImageDraw.Draw(mask_bg)
            mask_bg_draw.rounded_rectangle(
                (0, 0, ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT),
                radius=ProfileConfig.CARD_RADIUS,
                fill=255
            )
            background_image.putalpha(mask_bg)
            logger.info("Background Loading: Solid color fallback background created due to local file not found.")
        except Exception as e:
            logger.error(f"Background Loading: Failed to load/process local background from '{ProfileConfig.DEFAULT_LOCAL_BG_PATH}' due to generic error: {e}. Using solid color fallback.", exc_info=True)
            background_image = Image.new('RGBA', (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), (50, 50, 70, 255))
            mask_bg = Image.new('L', (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), 0)
            mask_bg_draw = ImageDraw.Draw(mask_bg)
            mask_bg_draw.rounded_rectangle(
                (0, 0, ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT),
                radius=ProfileConfig.CARD_RADIUS,
                fill=255
            )
            background_image.putalpha(mask_bg)
            logger.info("Background Loading: Solid color fallback background created due to general error.")

        if background_image:
            base_image.paste(background_image, (0, 0), background_image)
            logger.debug("Background image pasted onto base card.")
        else:
            logger.error("Background Loading: No background image was determined to be pasted (this should not happen if fallbacks work).")

        avatar_image = None
        try:
            logger.debug(f"Avatar Collection: Step 1 - Attempting to get profile photos for user ID: {user.id} from Telegram.")
            photos = await bot_instance.get_user_profile_photos(user.id, limit=1)
            
            if photos.photos and photos.photos[0]:
                logger.debug(f"Avatar Collection: Step 2 - Profile photos found. Number of photos: {len(photos.photos[0])}. Selecting the largest one.")
                file_id = photos.photos[0][-1].file_id
                logger.debug(f"Avatar Collection: Step 3 - File ID of the largest photo: {file_id}.")
                
                file = await bot_instance.get_file(file_id)
                file_path = file.file_path
                logger.debug(f"Avatar Collection: Step 4 - File path received from Telegram: {file_path}.")

                if file_path:
                    avatar_bytes = BytesIO()
                    logger.debug(f"Avatar Collection: Step 5 - Downloading file from path: {file_path}.")
                    
                    await bot_instance.download_file(file_path, destination=avatar_bytes, timeout=aiohttp.ClientTimeout(total=10))
                    avatar_bytes.seek(0)
                    
                    logger.debug("Avatar Collection: Step 6 - Image downloaded. Opening with PIL and converting to RGBA.")
                    avatar_image = Image.open(avatar_bytes).convert("RGBA")
                    
                    logger.debug(f"Avatar Collection: Step 7 - Resizing avatar to {ProfileConfig.AVATAR_SIZE}x{ProfileConfig.AVATAR_SIZE}.")
                    avatar_image = avatar_image.resize((ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE))
                    
                    logger.debug("Avatar Collection: Step 8 - Creating circular mask for the avatar.")
                    mask = Image.new("L", avatar_image.size, 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), fill=255)
                    
                    logger.debug("Avatar Collection: Step 9 - Applying mask to make avatar circular.")
                    avatar_image = ImageOps.fit(avatar_image, mask.size, centering=(0.5, 0.5))
                    avatar_image.putalpha(mask)
                    logger.info(f"Avatar Collection: Successfully loaded and processed user avatar for user {user.id}.")
                else:
                    logger.warning(f"Avatar Collection: Step 4.1 - File path was empty for avatar of user {user.id}. Initiating fallback to default placeholder.")
                    raise ValueError("File path not available")
            else:
                logger.info(f"Avatar Collection: Step 2.1 - No profile photos found for user {user.id}. Initiating fallback to default placeholder.")
                raise ValueError("No profile photos")
        
        except Exception as e:
            logger.warning(f"Avatar Collection: Primary avatar retrieval failed for user {user.id}: {e}. Attempting to load default placeholder from URL.", exc_info=True)
            try:
                logger.debug(f"Avatar Collection: Fallback Step 1 - Attempting to download default avatar from URL: {ProfileConfig.DEFAULT_AVATAR_URL}.")
                timeout = aiohttp.ClientTimeout(total=10) 
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(ProfileConfig.DEFAULT_AVATAR_URL) as resp: 
                        resp.raise_for_status()
                        avatar_placeholder_data = await resp.read()
                
                logger.debug("Avatar Collection: Fallback Step 2 - Default avatar downloaded. Opening with PIL and converting to RGBA.")
                avatar_image = Image.open(BytesIO(avatar_placeholder_data)).convert("RGBA")
                
                logger.debug(f"Avatar Collection: Fallback Step 3 - Resizing default avatar to {ProfileConfig.AVATAR_SIZE}x{ProfileConfig.AVATAR_SIZE}.")
                avatar_image = avatar_image.resize((ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE))
                
                logger.debug("Avatar Collection: Fallback Step 4 - Creating circular mask for the default avatar.")
                mask = Image.new("L", avatar_image.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), fill=255)
                
                logger.debug("Avatar Collection: Fallback Step 5 - Applying mask to default avatar to make it circular.")
                avatar_image = ImageOps.fit(avatar_image, mask.size, centering=(0.5, 0.5))
                avatar_image.putalpha(mask)
                logger.info("Avatar Collection: Default avatar placeholder loaded successfully from URL.")
            
            except Exception as e_fallback:
                logger.error(f"Avatar Collection: Critical Fallback Failed! Could not load default avatar placeholder from URL '{ProfileConfig.DEFAULT_AVATAR_URL}': {e_fallback}. Using solid gray fallback.", exc_info=True)
                logger.debug(f"Avatar Collection: Final Fallback - Creating a solid gray {ProfileConfig.AVATAR_SIZE}x{ProfileConfig.AVATAR_SIZE} square as avatar.")
                avatar_image = Image.new('RGBA', (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), (100, 100, 100, 255)) 
                logger.info("Avatar Collection: Using a solid gray square as the final fallback avatar.")

        if avatar_image:
            logger.debug("Avatar Collection: Pasting the determined avatar image onto the base card image.")
            base_image.paste(avatar_image, ProfileConfig.AVATAR_OFFSET, avatar_image)
            logger.debug("Avatar pasted onto base image.")
        else:
            logger.error("Avatar Collection: No avatar image was determined to be pasted (this should not happen if fallbacks work).")

        coin_icon_offset_x = ProfileConfig.AVATAR_X + ProfileConfig.AVATAR_SIZE - 25
        coin_icon_offset_y = ProfileConfig.AVATAR_Y + ProfileConfig.AVATAR_SIZE - 25
        draw_base.ellipse((coin_icon_offset_x, coin_icon_offset_y, 
                        coin_icon_offset_x + 20, coin_icon_offset_y + 20), 
                        fill=(255, 215, 0))
        draw_base.text((coin_icon_offset_x + 5, coin_icon_offset_y + 2), "$", font=font_small, fill=(0,0,0))
        logger.debug("Coin icon drawn on avatar.")

        def draw_text_with_shadow(draw_obj, position, text, font, text_color, shadow_color, shadow_offset=(1, 1)):
            shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
            draw_obj.text(shadow_pos, text, font=font, fill=shadow_color)
            draw_obj.text(position, text, font=font, fill=text_color)
            logger.debug(f"Text '{text}' drawn with shadow at {position}.")
        
        display_name = profile.get('display_name', user.first_name) 
        level = profile.get('level', 1)
        exp = profile.get('exp', 0)
        lumcoins = profile.get('lumcoins', 0)
        hp = profile.get('hp', 100)
        total_messages = profile.get('total_messages', 0)
        flames = profile.get('flames', 0)
        logger.debug(f"Profile data for image: Display Name: {display_name}, Level: {level}, EXP: {exp}, Lumcoins: {lumcoins}, HP: {hp}.")

        username_text = f"{display_name}" 
        
        draw_text_with_shadow(draw_base, (ProfileConfig.TEXT_BLOCK_LEFT_X, ProfileConfig.USERNAME_Y), 
                            username_text, font_large, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Left-central text block (username) drawn.")

        needed_exp_for_next_level = self._get_exp_for_level(level)

        draw_text_with_shadow(draw_base, (ProfileConfig.EXP_BAR_X, ProfileConfig.EXPERIENCE_LABEL_Y),
                            "Experience", font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Experience label drawn.")

        exp_bar_rect = (ProfileConfig.EXP_BAR_X, ProfileConfig.EXP_BAR_Y,
                        ProfileConfig.EXP_BAR_X + ProfileConfig.EXP_BAR_WIDTH, ProfileConfig.EXP_BAR_Y + ProfileConfig.EXP_BAR_HEIGHT)
        
        current_exp_percentage = exp / needed_exp_for_next_level if needed_exp_for_next_level > 0 and level < ProfileConfig.MAX_LEVEL else (1.0 if level == ProfileConfig.MAX_LEVEL else 0.0)
        exp_bar_fill_width = int(ProfileConfig.EXP_BAR_WIDTH * current_exp_percentage)
        logger.debug(f"EXP Bar: current_exp_percentage={current_exp_percentage}, fill_width={exp_bar_fill_width}.")
        
        draw_base.rounded_rectangle(
            exp_bar_rect,
            radius=ProfileConfig.EXP_BAR_HEIGHT // 2, 
            fill=(50, 50, 50, 128)
        )
        logger.debug("EXP bar background drawn.")

        for i in range(exp_bar_fill_width):
            r = int(ProfileConfig.EXP_GRADIENT_START[0] + (ProfileConfig.EXP_GRADIENT_END[0] - ProfileConfig.EXP_GRADIENT_START[0]) * (i / ProfileConfig.EXP_BAR_WIDTH))
            g = int(ProfileConfig.EXP_GRADIENT_START[1] + (ProfileConfig.EXP_GRADIENT_END[1] - ProfileConfig.EXP_GRADIENT_START[1]) * (i / ProfileConfig.EXP_BAR_WIDTH))
            b = int(ProfileConfig.EXP_GRADIENT_START[2] + (ProfileConfig.EXP_GRADIENT_END[2] - ProfileConfig.EXP_GRADIENT_START[2]) * (i / ProfileConfig.EXP_BAR_WIDTH))
            draw_base.line([(exp_bar_rect[0] + i, exp_bar_rect[1]),
                            (exp_bar_rect[0] + i, exp_bar_rect[3])],
                        fill=(r, g, b, ProfileConfig.EXP_BAR_ALPHA), width=1)
        logger.debug("EXP bar filled with green gradient with transparency.")
        
        exp_progress_text = f"{exp}/{needed_exp_for_next_level}"
        exp_progress_text_bbox = draw_base.textbbox((0,0), exp_progress_text, font=font_medium)
        exp_progress_pos_x = ProfileConfig.EXP_BAR_X + ProfileConfig.EXP_BAR_WIDTH + (ProfileConfig.MARGIN // 2)
        exp_progress_pos_y = ProfileConfig.EXP_BAR_Y + (ProfileConfig.EXP_BAR_HEIGHT - (exp_progress_text_bbox[3] - exp_progress_text_bbox[1])) // 2
        draw_text_with_shadow(draw_base, (exp_progress_pos_x, exp_progress_pos_y),
                            exp_progress_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug(f"Experience progress text '{exp_progress_text}' drawn.")


        hp_right_text = "HP"
        hp_value_text = f"❤️ {hp}"
        
        hp_right_text_bbox = draw_base.textbbox((0,0), hp_right_text, font=font_medium)
        hp_right_text_width = hp_right_text_bbox[2] - hp_right_text_bbox[0]
        hp_right_x = ProfileConfig.RIGHT_COLUMN_X - hp_right_text_width
        draw_text_with_shadow(draw_base, (hp_right_x, ProfileConfig.RIGHT_COLUMN_TOP_Y), 
                            hp_right_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        
        hp_value_text_bbox = draw_base.textbbox((0,0), hp_value_text, font=font_xlarge)
        hp_value_text_width = hp_value_text_bbox[2] - hp_value_text_bbox[0]
        hp_value_x = ProfileConfig.RIGHT_COLUMN_X - hp_value_text_width
        draw_text_with_shadow(draw_base, (hp_value_x, ProfileConfig.RIGHT_COLUMN_TOP_Y + 25),
                            hp_value_text, font_xlarge, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Right column HP text drawn.")

        lumcoins_right_text = "LumCoins"
        lumcoins_value_text = f"₽ {lumcoins}"
        
        lumcoins_right_text_bbox = draw_base.textbbox((0,0), lumcoins_right_text, font=font_medium)
        lumcoins_right_text_width = lumcoins_right_text_bbox[2] - lumcoins_right_text_bbox[0]
        lumcoins_right_x = ProfileConfig.RIGHT_COLUMN_X - lumcoins_right_text_width
        lumcoins_y = ProfileConfig.RIGHT_COLUMN_TOP_Y + ProfileConfig.ITEM_SPACING_Y
        draw_text_with_shadow(draw_base, (lumcoins_right_x, lumcoins_y), 
                            lumcoins_right_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        
        lumcoins_value_text_bbox = draw_base.textbbox((0,0), lumcoins_value_text, font=font_xlarge)
        lumcoins_value_text_width = lumcoins_value_text_bbox[2] - lumcoins_value_text_bbox[0]
        lumcoins_value_x = ProfileConfig.RIGHT_COLUMN_X - lumcoins_value_text_width
        draw_text_with_shadow(draw_base, (lumcoins_value_x, lumcoins_y + 25),
                            lumcoins_value_text, font_xlarge, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Right column Lumcoins text drawn.")

        byte_io = BytesIO()
        base_image.save(byte_io, format='PNG')
        byte_io.seek(0)
        logger.info(f"Profile image generation completed for user {user.id}.")
        return byte_io

    async def update_lumcoins(self, user_id: int, amount: int):
        logger.debug(f"Updating Lumcoins for user {user_id} by amount {amount}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to update Lumcoins.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET lumcoins = lumcoins + ?
        WHERE user_id = ?
        ''', (amount, user_id))
        await self._conn.commit()
        logger.info(f"Lumcoins updated for user {user_id}. Change: {amount}.")

    async def get_lumcoins(self, user_id: int) -> int:
        logger.debug(f"Fetching Lumcoins for user {user_id}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to get Lumcoins.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT lumcoins FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        lumcoins_value = result[0] if result else 0
        logger.info(f"Lumcoins for user {user_id}: {lumcoins_value}.")
        return lumcoins_value

    def get_available_backgrounds(self) -> Dict[str, Dict[str, Any]]:
        logger.debug("Retrieving available backgrounds from shop configuration.")
        return ProfileConfig.BACKGROUND_SHOP

    async def get_last_work_time(self, user_id: int) -> float:
        logger.debug(f"Fetching last work time for user {user_id}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to get last work time.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT last_work_time FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        last_work = result[0] if result else 0.0
        logger.info(f"Last work time for user {user_id}: {last_work}.")
        return last_work

    async def update_last_work_time(self, user_id: int, timestamp: float):
        logger.debug(f"Updating last work time for user {user_id} to {timestamp}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to update last work time.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET last_work_time = ?
        WHERE user_id = ?
        ''', (timestamp, user_id))
        await self._conn.commit()
        logger.info(f"Last work time updated for user {user_id} to {timestamp}.")
    
    async def set_level(self, user_id: int, level: int):
        logger.debug(f"Attempting to set level for user {user_id} to {level}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to set level.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        
        level = max(1, min(level, ProfileConfig.MAX_LEVEL))
        logger.debug(f"Level for user {user_id} adjusted to {level} (within bounds).")
        
        needed_exp = self._get_exp_for_level(level)
        
        await cursor.execute('''
        UPDATE user_profiles
        SET level = ?, exp = ?
        WHERE user_id = ?
        ''', (level, needed_exp, user_id))
        await self._conn.commit()
        logger.info(f"User {user_id} level set to {level} with exp {needed_exp}.")

    async def set_hp(self, user_id: int, hp_value: int):
        logger.debug(f"Attempting to set HP for user {user_id} to {hp_value} via database.py.")
        hp_value = max(ProfileConfig.MIN_HP, min(hp_value, ProfileConfig.MAX_HP)) 
        await self.update_user_rp_stats(user_id, hp=hp_value)
        logger.info(f"User {user_id} HP set to {hp_value} via database.py.")

    async def update_user_rp_stats(self, user_id: int, **kwargs: Optional[Any]) -> None:
        from database import update_user_rp_stats as db_update_user_rp_stats
        await db_update_user_rp_stats(user_id, **kwargs)

    async def get_top_users_by_level(self, limit: int = 10) -> List[Dict[str, Any]]:
        logger.debug(f"Fetching top {limit} users by level.")
        if self._conn is None:
            logger.error("Database connection not established when trying to get top users by level.")
            raise RuntimeError("Database connection is not established.")
        
        cursor = await self._conn.cursor()
        await cursor.execute('''
            SELECT
                up.user_id,
                u.username,
                u.first_name,
                up.level,
                up.exp
            FROM user_profiles up
            JOIN users u ON up.user_id = u.user_id
            ORDER BY up.level DESC, up.exp DESC
            LIMIT ?
        ''', (limit,))
        
        rows = await cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        top_users = []
        for row in rows:
            user_data = dict(zip(columns, row))
            user_data['display_name'] = f"@{user_data['username']}" if user_data['username'] else user_data['first_name']
            top_users.append(user_data)
        logger.info(f"Retrieved top {len(top_users)} users by level.")
        return top_users

    async def get_top_users_by_lumcoins(self, limit: int = 10) -> List[Dict[str, Any]]:
        logger.debug(f"Fetching top {limit} users by lumcoins.")
        if self._conn is None:
            logger.error("Database connection not established when trying to get top users by lumcoins.")
            raise RuntimeError("Database connection is not established.")
        
        cursor = await self._conn.cursor()
        await cursor.execute('''
            SELECT
                up.user_id,
                u.username,
                u.first_name,
                up.lumcoins
            FROM user_profiles up
            JOIN users u ON up.user_id = u.user_id
            ORDER BY up.lumcoins DESC
            LIMIT ?
        ''', (limit,))
        
        rows = await cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        top_users = []
        for row in rows:
            user_data = dict(zip(columns, row))
            user_data['display_name'] = f"@{user_data['username']}" if user_data['username'] else user_data['first_name']
            top_users.append(user_data)
        logger.info(f"Retrieved top {len(top_users)} users by lumcoins.")
        return top_users
