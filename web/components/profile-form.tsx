"use client";

import { useState } from "react";

import type { UserStateSnapshot } from "../lib/personal-opportunities";

interface ProfileFormProps {
  initialState: UserStateSnapshot | null;
  action: (formData: FormData) => void | Promise<void>;
  returnTo?: string;
}

export default function ProfileForm({ initialState, action, returnTo = "/me/opportunities" }: ProfileFormProps) {
  const initiallySkipped =
    initialState?.skipped_fields.includes("major_name") ?? false;
  const [skipMajor, setSkipMajor] = useState(initiallySkipped);
  return (
    <form className="profile-form" action={action} aria-describedby="profile-privacy-note">
      <input type="hidden" name="return_to" value={returnTo} />
      <p id="profile-privacy-note" className="privacy-note">
        只收集当前资格与行动所需信息。可选字段可以跳过；缺失不会默认成不符合。
      </p>
      <fieldset>
        <legend>当前阶段与目标</legend>
        <div className="form-grid">
          <label>
            当前阶段（可跳过）
            <select name="life_stage" defaultValue={initialState?.life_stage ?? ""}>
              <option value="">暂不提供</option>
              <option value="STUDENT">在校</option>
              <option value="GRADUATING">应届/临近毕业</option>
              <option value="EARLY_CAREER">职场早期</option>
              <option value="UNEMPLOYED">待业</option>
              <option value="OTHER">其他</option>
            </select>
          </label>
          <label>
            当前目标（可跳过）
            <select name="goal_type" defaultValue={initialState?.goal_types[0] ?? ""}>
              <option value="">暂不提供</option>
              <option value="PUBLIC_SERVICE_EMPLOYMENT">公共部门就业</option>
              <option value="STATE_OWNED_ENTERPRISE_EMPLOYMENT">国央企就业</option>
              <option value="POLICY_BENEFIT">政策权益</option>
              <option value="GROWTH_PROGRAM">成长计划</option>
            </select>
          </label>
          <label>
            学历（可跳过）
            <select
              name="education_level"
              defaultValue={initialState?.attributes.education_level ?? ""}
            >
              <option value="">暂不提供</option>
              <option value="SECONDARY">高中及以下</option>
              <option value="ASSOCIATE">专科</option>
              <option value="BACHELOR">本科</option>
              <option value="MASTER">硕士</option>
              <option value="DOCTORATE">博士</option>
            </select>
          </label>
          <label>
            毕业年份（可跳过）
            <input
              name="graduation_year"
              type="number"
              inputMode="numeric"
              min="1980"
              max="2100"
              defaultValue={initialState?.attributes.graduation_year ?? ""}
            />
          </label>
          <label>
            学生状态（可跳过）
            <select
              name="student_status"
              defaultValue={initialState?.attributes.student_status ?? ""}
            >
              <option value="">暂不提供</option>
              <option value="ENROLLED">在读</option>
              <option value="GRADUATING">应届</option>
              <option value="RECENT_GRADUATE">近期毕业</option>
              <option value="EMPLOYED">在职</option>
              <option value="OTHER">其他</option>
            </select>
          </label>
          <label>
            现居地（可跳过）
            <input
              name="residence_region"
              maxLength={80}
              defaultValue={initialState?.attributes.residence_region ?? ""}
            />
          </label>
        </div>
      </fieldset>
      <fieldset>
        <legend>专业信息</legend>
        <label className="check-label">
          <input
            name="skip_major"
            type="checkbox"
            checked={skipMajor}
            onChange={(event) => setSkipMajor(event.currentTarget.checked)}
          />
          暂时跳过专业信息
        </label>
        {!skipMajor ? (
          <div className="form-grid">
            <label>
              专业名称（可跳过）
              <input
                name="major_name"
                maxLength={80}
                defaultValue={initialState?.attributes.major_name ?? ""}
              />
            </label>
            <label>
              专业代码（可跳过）
              <input
                name="major_code"
                maxLength={32}
                defaultValue={initialState?.attributes.major_code ?? ""}
              />
            </label>
          </div>
        ) : null}
      </fieldset>
      <fieldset>
        <legend>软偏好（只影响顺序）</legend>
        <p className="field-help">这些值不会改变资格四态，也不会覆盖硬性冲突。</p>
        <div className="form-grid">
          <label>
            优先地区（可跳过）
            <input
              name="preference_region"
              maxLength={80}
              defaultValue={initialState?.preference_regions[0] ?? ""}
            />
          </label>
          <label>
            优先机会类型（可跳过）
            <select
              name="preference_type"
              defaultValue={initialState?.preference_types[0] ?? ""}
            >
              <option value="">暂不提供</option>
              <option value="PUBLIC_INSTITUTION_JOB">事业单位招聘</option>
              <option value="STATE_OWNED_ENTERPRISE_JOB">国央企校招</option>
              <option value="YOUTH_POLICY_BENEFIT">青年政策权益</option>
              <option value="GRASSROOTS_PROGRAM">基层项目</option>
            </select>
          </label>
        </div>
        <label className="check-label">
          <input
            name="personalization_enabled"
            type="checkbox"
            defaultChecked={initialState?.personalization_enabled ?? true}
          />
          允许软偏好参与个人排序
        </label>
      </fieldset>
      <button className="button button-primary" type="submit">
        保存画像并重新判断
      </button>
    </form>
  );
}
