"""Analysis report subprocess for policy checklist formatting and reporting."""

import os

import pandas as pd
from fpdf import FPDF


def generate_policy_report(
    checklist: str = None,
    options: dict = {'language': 'English'},
):
    """Generate a policy report for a completed policy checklist."""
    import time

    import subprocesses.ghsci as ghsci
    from subprocesses._utils import generate_scorecard, get_and_setup_font

    if checklist is None:
        print(
            '\nThe path to a completed policy review checklist Excel file has not been provided as an argument, and so the example file will be used for demonstration purposes.',
        )
        r = ghsci.example()
        checklist = r.config['policy_review']
        print(
            "To generate your own report, please add `checklist='path_to_your_checklist'` when next running this function.\n",
        )
    else:
        ## Derive a Region object with required info
        # r.config['policy_review'] = checklist
        r = ghsci.Region('example_ES_Las_Palmas_2023')
        print(
            f'Generating a policy report based on: {checklist})\n',
        )
        # return None
    if 'language' not in options:
        print('No language specified; defaulting to English.')
        language = 'English'
    else:
        language = options['language']
        if language not in r.config['reporting']['languages']:
            r.config['reporting']['languages'][language] = {}
        if language not in r.config['reporting']['exceptions']:
            r.config['reporting']['exceptions'][language] = {}
    r.config['policy_review'] = checklist
    if not os.path.isfile(r.config['policy_review']):
        print(
            f"The specified policy checklist file ({r.config['policy_review']}) could not be found. Please check the file path is correct and try again.",
        )
        return None
    policy_setting = get_policy_setting(r.config['policy_review'])
    r.codename = policy_setting['City']
    r.name = policy_setting['City']
    r.config['codename'] = policy_setting['City']
    r.config['name'] = policy_setting['City']
    r.config['year'] = policy_setting['Date']
    if str(r.config['year']) in ['nan', 'NaN', '']:
        r.config['year'] = time.strftime('%Y-%m-%d')
    r.config['region_dir'] = './data'
    # r.config['reporting']['images'] = {}
    r.config['reporting']['languages'][language]['name'] = policy_setting[
        'City'
    ]
    r.config['reporting']['languages'][language]['country'] = policy_setting[
        'Country'
    ]
    r.config['reporting']['exceptions'][language]['author_names'] = (
        policy_setting['Person(s)']
    )
    policy_review = policy_data_setup(
        r.config['policy_review'],
    )
    report_template = 'policy'
    if policy_review is None:
        print(
            f"The policy checklist ({r.config['policy_review']}) could not be loaded.",
        )
        return None
    if 'images' in options:
        r.config['reporting']['images'] = options['images']
        print(
            f'\nCustom image configuration:\n{r.config["reporting"]["images"]}',
        )
    if 'context' in options:
        r.config['reporting']['languages'][language]['context'] = options[
            'context'
        ]
        print(
            f'\nCustom context:\n{r.config["reporting"]["languages"][language]["context"]}',
        )
    if 'summary' in options:
        r.config['reporting']['languages'][language]['summary_policy'] = (
            options['summary']
        )
        print(
            f'\nCustom summary:\n{r.config["reporting"]["languages"][language]["summary_policy"]}',
        )
    if 'summary_policy' in options:
        r.config['reporting']['languages'][language]['summary_policy'] = (
            options['summary_policy']
        )
        print(
            f'\nCustom summary:\n{r.config["reporting"]["languages"][language]["summary_policy"]}',
        )
    if 'exceptions' in options:
        r.config['reporting']['exceptions'][language] = options['exceptions']
        print(
            f"\nCustom exceptions:\n{r.config['reporting']['exceptions'][language]}",
        )
    if 'publication_ready' in options:
        r.config['reporting']['publication_ready'] = options[
            'publication_ready'
        ]
    phrases = r.get_phrases(language)
    font = get_and_setup_font(language, r.config)
    report = generate_scorecard(
        r,
        phrases,
        ghsci.indicators,
        policy_review,
        language,
        report_template,
        font,
    )
    print(f"Report saved to {report.replace('/home/ghsci/', '')}")
    return report


def _checklist_policy_identified(policy):
    """Check if policy identified.

    If any policy name entered for a particular measure ('Yes'); otherwise, 'None identified'.
    """
    identified = any(
        ~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']),
    )
    return ['✘', '✔'][identified]


def _checklist_policy_aligns(policy):
    """Check if policy aligns with healthy and sustainable cities principles.

    Yes: If policy details not entered under 'no' principles (qualifier!='No'; noting some policies aren't yes or no)

    No: If a policy identified with details entered under 'no' principles, without an aligned policy identified

    Mixed: If both 'yes' (and aligned) and 'no' principles identified
    """
    # policy_count = len(policy.query("""qualifier!='No'"""))
    identified = any(
        ~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']),
    )
    aligns = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and qualifier!='No'""",
        )['Policy'],
    )
    does_not_align = any(
        policy.query(
            """
            Policy.astype('str') not in ['No','','nan','NaN'] and ((qualifier=='No') or (qualifier!='No' and `Evidence-informed threshold`.astype('str') in ['No']))
            """,
        )['Policy'],
    )
    # if aligns_count == policy_count:
    #     return '✔'
    if aligns and does_not_align:
        return '✔/✘'
    elif aligns:
        return '✔'
        # return f'✔ ({aligns_count}/{policy_count})'
    elif identified and (not aligns or does_not_align):
        return '✘'
    else:
        return '-'


def _checklist_policy_measurable(policy):
    """Check if policy has a measurable target."""
    identified = any(
        ~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']),
    )
    measurable = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Measurable target`.astype('str') not in ['No','','nan','NaN','Unclear']""",
        )['Policy'],
    )
    not_measurable = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Measurable target`.astype('str') in ['No','','nan','NaN','Unclear']""",
        )['Policy'],
    )
    if measurable and not_measurable:
        return '✔'
        # return '✔+✘'
    elif measurable:
        return '✔'
    elif identified and (not measurable or not_measurable):
        return '✘'
    else:
        return '-'


def _checklist_policy_evidence(policy):
    """Check if policy has an evidence informed threshold target."""
    identified = any(
        ~policy['Policy'].astype(str).isin(['No', '', 'nan', 'NaN']),
    )
    evidence = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Evidence-informed threshold`.astype('str') not in ['No','','nan','NaN']""",
        )['Policy'],
    )
    not_evidence = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and `Evidence-informed threshold`.astype('str') in ['No','','nan','NaN']""",
        )['Policy'],
    )
    if evidence and not_evidence:
        return '✔+✘'
    elif evidence:
        return '✔'
    elif identified and (not evidence or not_evidence):
        return '✘'
    else:
        return '-'


def policy_data_setup(xlsx: str):
    """Returns a dictionary of policy data."""
    if xlsx in [
        None,
        '',
        '/home/ghsci/process/data/policy_review/gohsc-policy-indicator-checklist.xlsx',
    ]:
        print(
            'No policy checklist file provided; policy review will be skipped.',
        )
        return None
    policies = get_policies('2.0.0')
    # get list of all valid measures
    measures = [
        measure
        for categories in [
            policies['Checklist'][x] for x in policies['Checklist']
        ]
        for measure in categories
    ]
    # read in completed policy checklist
    audit = get_policy_checklist(xlsx)

    if audit is not None:
        # restrict policy checklist to valid measures
        audit = audit.loc[audit['Measures'].isin(measures)]
    else:
        print('Policy checklist evaluation will be skipped.')
        return None
    # initialise and populate checklist for specific themes
    checklist = {}
    for topic in policies['Checklist']:
        checklist[topic] = pd.DataFrame.from_dict(
            policies['Checklist'][topic],
        ).set_index(0)
        checklist[topic].index.name = 'Measure'
        # initialise criteria columns
        checklist[topic]['identified'] = '-'
        checklist[topic]['aligns'] = '-'
        checklist[topic]['measurable'] = '-'
        for measure in checklist[topic].index:
            if audit is not None:
                policy_measure = audit.query(
                    f'Measures == "{measure}" and not Policy.isna()',
                )
                # evaluate indicators against criteria
                checklist[topic].loc[
                    measure,
                    'identified',
                ] = _checklist_policy_identified(policy_measure)
                checklist[topic].loc[
                    measure,
                    'aligns',
                ] = _checklist_policy_aligns(policy_measure)
                checklist[topic].loc[
                    measure,
                    'measurable',
                ] = _checklist_policy_measurable(policy_measure)
                # checklist[topic].loc[measure,'evidence'] = _checklist_policy_evidence(policy_measure)
            else:
                checklist[topic].loc[
                    measure,
                    ['identified', 'aligns', 'measurable'],
                ] = '-'
    # Replace all '✘' with '-' for topics where all criteria are '✘'
    for topic in checklist:
        if (checklist[topic]['identified'] == '✘').all():
            checklist[topic]['identified'] = checklist[topic][
                'identified'
            ].replace('✘', '-')
    return checklist


def get_policy_presence_quality_score_dictionary(xlsx):
    """
    Returns a dictionary with scores for presence and quality of policy data.

    Only unique measures are evaluated (ie. if a measure is reported multiple themes, only its highest rating instance is evaluated).

    'Transport and planning combined in one government department' is excluded from quality rating.

    Quality scores for 'aligns':
    - '✔': 1
    - '✔/✘': -0.5
    - '✘': -1

    Quality scores for 'measurable':
    - no relevant policy = 0;
    - policy but 'no' measurable target = 1;
    - policy with 'yes' measurable target = 2.

    Final quality score for measures is the product of the 'align score' and 'measurable score'.

    Overall quality score is the sum of the quality scores for each measure.
    """
    # read in completed policy checklist
    audit = get_policy_checklist(xlsx)
    if audit is None:
        print(
            f'Policy document does not appear to have been completed and evaluation will be skipped.  Check the configured document {xlsx} is complete to proceed.',
        )
        return None
    # initialise and populate checklist for specific themes
    checklist = pd.DataFrame.from_dict(audit['Measures'].unique()).set_index(0)
    checklist.index.name = 'Measure'
    # initialise criteria columns
    checklist['identified'] = '-'
    checklist['aligns'] = '-'
    checklist['measurable'] = '-'
    for measure in checklist.index:
        if audit is not None:
            policy_measure = audit.query(f'Measures == "{measure}"')
            # evaluate indicators against criteria
            checklist.loc[measure, 'identified'] = (
                _checklist_policy_identified(
                    policy_measure,
                )
            )
            checklist.loc[measure, 'aligns'] = _checklist_policy_aligns(
                policy_measure,
            )
            checklist.loc[
                measure,
                'measurable',
            ] = _checklist_policy_measurable(policy_measure)
            # checklist.loc[measure,'evidence'] = _checklist_policy_evidence(policy_measure)
        else:
            checklist.loc[measure, ['identified', 'aligns', 'measurable']] = (
                '-'
            )
    checklist['align_score'] = checklist['aligns'].map(
        {'✔': 1, '✔/✘': -0.5, '✘': -1},
    )
    checklist['measurable_score'] = checklist['measurable'].map(
        {'✔': 2, '✘': 1, '-': 0},
    )
    checklist['quality'] = (
        checklist['align_score'] * checklist['measurable_score']
    )
    policy_score = {}
    policy_score['presence'] = {
        'numerator': (checklist['identified'] == '✔').sum(),
        'denominator': len(checklist),
    }
    policy_score['quality'] = {
        'numerator': checklist.loc[
            ~(
                checklist.index
                == 'Transport and planning combined in one government department'
            ),
            'quality',
        ].sum(),
        'denominator': len(
            checklist.loc[
                ~(
                    checklist.index
                    == 'Transport and planning combined in one government department'
                )
            ],
        )
        * 2,
    }
    return policy_score


def validate_policy_checklist(df: pd.DataFrame):
    """
    Run all policy checklist validation checks and report failures in plain language.

    Validates:
    1. Policies with details must have a policy name
    2. If measurable target is 'Yes', evidence threshold must be evaluated
    3. If evidence threshold is evaluated, measurable target must be 'Yes'

    Args:
        df: Policy checklist DataFrame

    Raises
    ------
        ValueError: If any validation checks fail, with detailed plain-language description
    """
    all_errors = []

    # Run all validation checks
    checks = [
        ('Missing policy names', validate_no_policy_lacking_policy_name),
        # ("Measurable targets without evidence evaluation", validate_no_policy_with_measurable_target_but_evidence_basis_not_evaluated),
        (
            'Evidence thresholds with non-Yes measurable targets',
            validate_if_evidence_informed_threshold_evaluated_measurable_is_yes,
        ),
    ]

    for check_name, check_func in checks:
        try:
            is_valid, errors = check_func(df)
            if not is_valid:
                all_errors.append((check_name, errors))
        except Exception as e:
            # If check raises exception for missing columns, re-raise
            if 'Missing required columns' in str(e):
                raise
            all_errors.append(
                (check_name, [(None, f"Check failed: {str(e)}")]),
            )

    # If there are any errors, format and raise them
    if all_errors:
        error_msg = 'Policy checklist validation failed:\n\n'

        for check_name, errors in all_errors:
            error_msg += f"❌ {check_name} ({len(errors)} issue{'s' if len(errors) != 1 else ''}):\n"
            for _, error_desc in errors:
                error_msg += f"   • {error_desc}\n"
            error_msg += '\n'

        error_msg += 'Please correct these issues and try again.'
        raise ValueError(error_msg)


def validate_if_evidence_informed_threshold_evaluated_measurable_is_yes(
    df: pd.DataFrame,
):
    """Validate that evidence informed threshold measures are also measurable.

    Validate that for non-null Policy rows:
    If 'Evidence-informed threshold' is answered (non-null),
    then 'Measurable target' must be 'Yes'.

    Returns: (is_valid, errors_list) where errors_list contains tuples of (row_index, error_description)
    """
    required_cols = [
        'Indicators',
        'Measures',
        'Policies',
        'Policy',
        'Measurable target',
        'Evidence-informed threshold',
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Only consider rows where Policy is not NA
    df_sub = df[df['Policy'].notna()]

    # Normalise Measurable target values to avoid case/whitespace issues
    mt = df_sub['Measurable target'].astype(str).str.strip().str.lower()

    inconsistent_mask = df_sub[
        'Evidence-informed threshold'
    ].notna() & ~mt.isin(['yes'])

    inconsistent_rows = df_sub[inconsistent_mask]

    errors = []
    for idx, row in inconsistent_rows.iterrows():
        errors.append(
            (
                idx,
                f"Row {idx + 3}: Indicator: {row['Indicators']}, Measure: {row['Measures']}, Policy: {row['Policy']}",
            ),
        )

    return len(errors) == 0, errors


def validate_no_policy_lacking_policy_name(df):
    """Validate that rows with policy details have a policy name.

    If any policy-related fields are filled (not 'Not applicable' and not all NA),
    then the Policy name should not be empty.

    Returns: (is_valid, errors_list) where errors_list contains tuples of (row_index, error_description)
    """
    required_cols = [
        'Indicators',
        'Measures',
        'Policies',
        'Policy',
        'Level of government',
        'Adoption date',
        'Citation',
        'Text',
        'Mandatory',
        'Measurable target',
        'Measurable target text',
        'Evidence-informed threshold',
        'Threshold explanation',
    ]

    # Get the columns after Policy (index 3) up to but not including qualifier (index -1)
    policy_detail_cols = required_cols[
        4:-1
    ]  # Excludes 'Policy' and 'qualifier'

    errors = []
    for idx, row in df.iterrows():
        # Check if any policy detail fields are filled
        detail_values = [
            row.get(col) for col in policy_detail_cols if col in df.columns
        ]
        has_details = any(
            pd.notna(val) and str(val).strip() not in ['', 'Not applicable']
            for val in detail_values
        )

        # Check if Policy name is missing or invalid
        policy_name = row.get('Policy')
        policy_empty = pd.isna(policy_name) or str(policy_name).strip() in ['']

        if has_details and policy_empty:
            errors.append(
                (
                    idx,
                    f"Row {idx + 3}: Indicator: {row.get('Indicators', 'N/A')}, Measure: {row.get('Measures', 'N/A')}",
                ),
            )

    return len(errors) == 0, errors


def validate_no_policy_with_measurable_target_but_evidence_basis_not_evaluated(
    df,
):
    """Validate policies with measurable targets are evaluated for evidence.

    Validate that for non-null Policy rows, if 'Measurable target' is 'Yes',
    then 'Evidence-informed threshold' is evaluated (not null).

    Returns: (is_valid, errors_list) where errors_list contains tuples of (row_index, error_description)
    """
    required_cols = [
        'Indicators',
        'Measures',
        'Policies',
        'Policy',
        'Measurable target',
        'Evidence-informed threshold',
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Only consider rows where Policy is not NA
    df_sub = df[df['Policy'].notna()]

    # Normalise Measurable target values to avoid case/whitespace issues
    mt = df_sub['Measurable target'].astype(str).str.strip().str.lower()

    inconsistent_mask = (mt == 'yes') & df_sub[
        'Evidence-informed threshold'
    ].isna()

    inconsistent_rows = df_sub[inconsistent_mask]

    errors = []
    for idx, row in inconsistent_rows.iterrows():
        errors.append(
            (
                idx,
                f"Row {idx + 3}: Indicator: {row['Indicators']}, Measure: {row['Measures']}, Policy: {row['Policy']}",
            ),
        )

    return len(errors) == 0, errors


def get_policy_checklist(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    setting = get_policy_setting(xlsx)
    policies = get_policies('2.0.0')

    try:
        if setting['Checklist version'] is None:
            print(
                'Unable to determine version of policy checklist; please check the confi3urel be skipped.',
            )
            return None
        elif setting['Checklist version'] < '2.0.0':
            print(
                'Checklist version is older than 2.0.0; attempting to read using legacy format.  Please check results carefully to confirm these are represented as intended.',
            )
            df = get_policy_checklist_legacy(xlsx)
        else:
            df = pd.read_excel(
                xlsx,
                sheet_name='Policy Checklist',
                header=2,
                usecols='A:M',
            )
            df.columns = [
                'Measures',
                'Policies',
                'Policy',
                'Level of government',
                'Adoption date',
                'Citation',
                'Text',
                'Mandatory',
                'Measurable target',
                'Measurable target text',
                'Evidence-informed threshold',
                'Threshold explanation',
                'Notes',
            ]
            df.insert(
                0,
                'Indicators',
                [
                    x if x in policies['Indicators'].keys() else pd.NA
                    for x in df['Measures']
                ],
            )
            # Strip redundant white space (e.g. at start or end of cell values that could impede matching or formatting)
            df = df.apply(
                lambda x: x.str.strip() if x.dtype == 'object' else x,
            )
            # fill down Indicators column values
            df.loc[:, ['Indicators', 'Measures']] = df.loc[
                :,
                ['Indicators', 'Measures'],
            ].ffill()
            # Exclude rows with NA for indicators
            df = df.loc[~df['Indicators'].isna()]
            # Exclude dataframe rows where indicators match measures (i.e. section headers)
            df = df.query('~(Indicators==Measures)').copy()
            # Add qualifier for evaluating policy polarity when scoring
            policy_qualifiers = (
                df['Policies'].isin([''])
                | df['Policies'].str.startswith('No')
                | df['Policies'].str.startswith('Yes')
            )
            df['qualifier'] = (
                df['Policies']
                .where(policy_qualifiers)
                .str.split(',')
                .str[0]
                .ffill()
                .fillna('')
            )
            # Exclude policy heading rows
            df = df.loc[~policy_qualifiers]
        # Run unified validation
        validate_policy_checklist(df)
        return df
    except Exception as e:
        print(
            f'  Error reading policy checklist; please ensure check that this has been completed following the directions.  Specific error: {e}',
        )
        return None


policies_2023 = {
    'Indicators': {
        'Integrated transport and urban planning actions to create healthy and sustainable cities': [
            'Transport and planning combined in one government department',
            'Explicit health-focused actions in urban policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Explicit health-focused actions in transport policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Health Impact Assessment requirements incorporated into urban/transport policy or legislation',
            'Urban and/or transport policy explicitly aims for integrated city planning',
        ],
        'Limit air pollution from land use and transport': [
            'Transport policies to limit air pollution',
            'Land use policies to reduce air pollution exposure',
        ],
        'Priority investment in public and active transport': [
            'Information on government expenditure on infrastructure for different transport modes',
        ],
        'City planning contributes to adaptation and mitigating \xa0the effects of climate change': [
            'Adaptation and disaster risk reduction strategies',
        ],
        'Appropriate context-specific housing densities that encourage walking; including higher density development around activity centres and transport hubs': [
            'Housing density requirements citywide or within close proximity to transport or town centres',
            'Height restrictions on residential buildings (min and/or max)',
            'Required urban growth boundary or maximum levels of greenfield housing development',
        ],
        'Limit car parking and price parking appropriately for context': [
            'Parking restrictions to discourage car use',
        ],
        'Diverse mix of housing types and local destinations needed for daily living': [
            'Mixture of local destinations for daily living',
            'Mixture of housing types and sizes',
        ],
        'Local destinations for healthy, walkable cities': [
            'Requirements for distance to daily living destinations',
            'Requirements for healthy food environments',
        ],
        'Crime prevention through urban design principles, manage traffic exposure, and establish urban greening provisions': [
            'Tree canopy and urban greening requirements',
            'Urban biodiversity protection & promotion',
            'Traffic safety requirements',
            'Crime prevention through environmental design requirements',
        ],
        'Create pedestrian- and cycling-friendly neighbourhoods, requiring highly connected street networks; pedestrian and cycling infrastructure provision; and public open space': [
            'Street connectivity requirements',
            'Pedestrian infrastructure provision requirements',
            'Cycling infrastructure provision requirements',
            'Walking participation targets',
            'Cycling participation targets',
            'Minimum requirements for public open space access',
        ],
        'Coordinated planning for transport, employment and infrastructure that ensures access by public transport': [
            'Requirements for public transport access to employment and services',
        ],
        'A balanced ratio of jobs to housing': [
            'Employment distribution requirements',
            'Requirements for ratio of jobs to housing',
        ],
        'Nearby, walkable access to public transport': [
            'Minimum requirements for public transport access',
            'Targets for public transport use',
        ],
    },
    'Checklist': {
        'Integrated city planning policies for health and sustainability': [
            'Explicit health-focused actions in transport policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Explicit health-focused actions in urban policy (i.e., explicit mention of health as a goal or rationale for an action)',
            'Health Impact Assessment requirements incorporated into urban/transport policy or legislation',
            'Urban and/or transport policy explicitly aims for integrated city planning',
            'Information on government expenditure on infrastructure for different transport modes',
        ],
        'Walkability and destination access related policies': [
            'Street connectivity requirements',
            'Parking restrictions to discourage car use',
            'Traffic safety requirements',
            'Pedestrian infrastructure provision requirements',
            'Cycling infrastructure provision requirements',
            'Walking participation targets',
            'Cycling participation targets',
            'Housing density requirements citywide or within close proximity to transport or town centres',
            'Height restrictions on residential buildings (min and/or max)',
            'Required urban growth boundary or maximum levels of greenfield housing development',
            'Mixture of housing types and sizes',
            'Mixture of local destinations for daily living',
            'Requirements for distance to daily living destinations',
            'Employment distribution requirements',
            'Requirements for ratio of jobs to housing',
            'Requirements for healthy food environments',
            'Crime prevention through environmental design requirements',
        ],
        'Public transport policy': [
            'Requirements for public transport access to employment and services',
            'Minimum requirements for public transport access',
            'Targets for public transport use',
        ],
        'Public open space policy': [
            'Minimum requirements for public open space access',
        ],
        'Urban air quality, and nature-based solutions policies': [
            'Transport policies to limit air pollution',
            'Land use policies to reduce air pollution exposure',
            'Tree canopy and urban greening requirements',
            'Urban biodiversity protection & promotion',
        ],
        'Climate disaster risk reduction policies': [
            'Adaptation and disaster risk reduction strategies',
        ],
    },
}


# 1) Indicator (group) name mapping: 2023 checklist → new checklist
checklist_indicator_map_2023_to_new = {
    'Integrated city planning policies for health and sustainability': 'Integrated city planning policies for health and sustainability',
    'Walkability and destination access related policies': 'Walkability and destination access policies',
    'Public transport policy': 'Public transport policies',
    'Public open space policy': 'Public open space policies',
    'Urban air quality, and nature-based solutions policies':
    # in the new schema these are split, but from the checklist POV
    # you can still map them primarily to Urban air quality policies
    'Urban air quality policies',
    'Climate disaster risk reduction policies': 'Climate disaster risk reduction policies',
}

# 2) Measure / item mapping: 2023 wording → new wording
checklist_measure_map_2023_to_new = {
    # Integrated city planning
    'Explicit health-focused actions in transport policy (i.e., explicit mention of health as a goal or rationale for an action)': "Transport policy with health-focused actions (i.e., explicit mention of the word 'health', 'wellbeing' or similar, as a goal or rationale for an action)",
    'Explicit health-focused actions in urban policy (i.e., explicit mention of health as a goal or rationale for an action)': "Urban policy with health-focused actions (i.e., explicit mention of the word 'health', 'wellbeing' or similar, as a goal or rationale for an action)",
    'Health Impact Assessment requirements incorporated into urban/transport policy or legislation': 'Health Impact Assessment (i.e., evaluating potential impacts of policies/plans on population health) requirements in urban/transport policy or legislation',
    'Information on government expenditure on infrastructure for different transport modes': 'Publicly available information on government expenditure for different transport modes',
    # Walkability & housing & destinations
    'Street connectivity requirements': 'Street connectivity',
    'Parking restrictions to discourage car use': 'Parking restrictions to discourage car use',
    'Traffic safety requirements': 'Traffic safety',
    'Pedestrian infrastructure provision requirements': 'Pedestrian infrastructure',
    'Cycling infrastructure provision requirements': 'Cycling infrastructure',
    'Walking participation targets': 'Walking participation',
    'Cycling participation targets': 'Cycling participation',
    'Housing density requirements citywide or within close proximity to transport or town centres': 'Housing or population density',
    'Height restrictions on residential buildings (min and/or max)': 'Residential building heights',
    'Required urban growth boundary or maximum levels of greenfield housing development': 'Limits on greenfield housing development',
    'Mixture of housing types and sizes': 'Mixture of housing types/sizes',
    'Mixture of local destinations for daily living': 'Mixture of local destinations for daily living',
    'Requirements for distance to daily living destinations': 'Close distance to daily living destinations',
    'Employment distribution requirements': 'Employment distribution',
    'Requirements for ratio of jobs to housing': 'Ratio of jobs to housing',
    'Requirements for healthy food environments': 'Healthy food environments',
    'Crime prevention through environmental design requirements': 'Crime prevention through environmental design',
    # Public transport
    'Requirements for public transport access to employment and services': 'Access to employment and services via public transport',
    'Minimum requirements for public transport access': 'Public transport access',
    'Targets for public transport use': 'Public transport use',
    # Public open space
    'Minimum requirements for public open space access': 'Public open space access',
    # Air quality / nature-based
    'Transport policies to limit air pollution': 'Transport policies to limit air pollution',
    'Land use policies to reduce air pollution exposure': 'Land use policies to reduce air pollution exposure',
    'Tree canopy and urban greening requirements': 'Tree canopy and urban greening',
    'Urban biodiversity protection & promotion': 'Urban biodiversity protection & promotion',
    # Climate
    'Adaptation and disaster risk reduction strategies': 'Adaptation and disaster risk reduction',
}

# 3) override which new indicator a particular measure belongs to (if
# the indicator group alone is not enough to route it correctly).
checklist_measure_indicator_override = {
    # Split the combined "Urban air quality, and nature-based solutions" category:
    'Tree canopy and urban greening requirements': 'Nature-based solutions policies',
    'Urban biodiversity protection & promotion': 'Nature-based solutions policies',
    'Transport policies to limit air pollution': 'Urban air quality policies',
    'Land use policies to reduce air pollution exposure': 'Urban air quality policies',
}


def get_policies(version):
    from ghsci import policies as ghsci_policies

    if version is None:
        raise ValueError(
            'Unable to determine version of policy checklist; please check the configured document is complete and includes the version number to proceed.',
        )
    elif version < '2.0.0':
        return policies_2023
    else:
        return ghsci_policies


def get_policy_checklist_legacy(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    policies = policies_2023
    try:
        df = pd.read_excel(
            xlsx,
            sheet_name='Policy Checklist',
            header=1,
            usecols='A:N',
        )
        df.columns = [
            'Indicators',
            'Measures',
            'Policies',
            'Policy',
            'Level of government',
            'Adoption date',
            'Citation',
            'Text',
            'Mandatory',
            'Measurable target',
            'Measurable target text',
            'Evidence-informed threshold',
            'Threshold explanation',
            'Notes',
        ]
        # Strip redundant white space (e.g. at start or end of cell values that could impede matching or formatting)
        df = df.apply(lambda x: x.str.strip() if x.dtype == 'object' else x)
        # Exclude dataframe rows where an indicator is defined without a corresponding measure
        # These are short name headings, and this is the quickest way to get rid of them!
        df = df.query('~(Indicators == Indicators and Measures != Measures)')
        # Remove the 'Public Open Space Policies' section that is nested within the Walkability section; it doesn't work well with the current formatting
        df = df.query('~(Measures=="PUBLIC OPEN SPACE POLICIES")')
        # fill down Indicators column values
        df.loc[:, 'Indicators'] = df.loc[:, 'Indicators'].ffill()
        # Only keep measures associated with indicators, replacing 'see also' reference indicators with NA
        df.loc[:, 'Measures'] = df.apply(
            lambda x: (
                x['Measures']
                if x['Indicators'] in policies['Indicators'].keys()
                and x['Measures'] in policies['Indicators'][x['Indicators']]
                else pd.NA
            ),
            axis=1,
        )
        # fill down Measures column values
        df.loc[:, 'Measures'] = df.loc[:, 'Measures'].ffill()
        df = df.loc[~df['Indicators'].isna()]
        df = df.loc[df['Indicators'] != 'Indicators']
        df['qualifier'] = (
            df['Policies']
            .apply(
                lambda x: (
                    x.strip()
                    if (
                        str(x).strip() == 'No'
                        or str(x).strip() == 'Yes'
                        or str(x).strip() == 'Yes, explicit mention of:'
                    )
                    else pd.NA
                ),
            )
            .ffill()
            .fillna('')
        )
        # replace df['qualifier'] with '' where df['Policies'] is in ['Yes','No'] (i.e. where df['Policies'] is a qualifier)
        df = df.loc[
            ~df['Policies'].isin(
                ['', 'No', 'Yes', 'Yes, explicit mention of:'],
            )
        ]
        # Remove measures ending in … (signifies that options are avilable in the subsequent rows)
        df = df.query('~(Measures.str.endswith("…"))')

        # 1. Map old indicator names → new indicator names
        df['Indicators'] = df['Indicators'].map(
            lambda x: checklist_indicator_map_2023_to_new.get(x, x),
        )

        # 2. Map old measures → new wording
        df['Measures'] = df['Measures'].map(
            lambda x: checklist_measure_map_2023_to_new.get(x, x),
        )

        # 3. Override indicator for specific measures to split air quality vs nature-based
        def override_indicator(row):
            m = row['Measures']
            if m in checklist_measure_indicator_override:
                return checklist_measure_indicator_override[m]
            return row['Indicators']

        df['Indicators'] = df.apply(override_indicator, axis=1)

        # (Optional) remove duplicates that might arise from merging categories
        df = df.drop_duplicates(
            subset=[
                'Indicators',
                'Measures',
                'Policies',
                'Policy',
                'Level of government',
                'Citation',
            ],
            keep='first',
        )
        return df
    except Exception as e:
        print(
            f'  Error reading policy checklist; please ensure these have been completed.  Specific error: {e}',
        )
        return None


def get_policy_setting(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    if xlsx in [
        None,
        '',
        '/home/ghsci/process/data/policy_review/gohsc-policy-indicator-checklist.xlsx',
    ]:
        print(
            'No policy checklist file provided; policy review will be skipped.',
        )
        return None
    if not os.path.isfile(xlsx):
        print(
            f'Policy checklist file not found at specified path {xlsx}; policy review will be skipped.',
        )
        return None
    try:
        df = pd.read_excel(xlsx, sheet_name='Collection details', header=3)
        if len(df.columns) < 3:
            print(
                'Policy checklist collection details appear not to have completed (no values found in column C); please check the specified file has been completed.',
            )
            return None
        setting = {}
        # Get version of checklist
        version = pd.read_excel(xlsx, sheet_name='Policy Checklist').iloc[0, 0]
        setting['Checklist version'] = (
            version.replace('version ', '').strip()
            if isinstance(version, str)
            else 'Unknown'
        )
        # Strip redundant white space (e.g. at start or end of cell values that could impede matching or formatting)
        df.columns = ['item', 'location', 'value']
        df.loc[:, 'item'] = df.loc[:, 'item'].ffill()
        setting['Person(s)'] = df.loc[
            df['item'] == 'Name of person(s) completing checklist:',
            'value',
        ].values[0]
        setting['E-mail'] = df.loc[
            df['item'] == 'Email address(es):',
            'value',
        ].values[0]
        setting['Date'] = df.loc[
            df['item'].str.replace(':', '') == 'Date completed',
            'value',
        ].values[0]
        try:
            setting['Date'] = setting['Date'].strftime('%Y')
        except Exception:
            pass
        if (
            'City, region and country the checklist has been used for:'
            in df['item'].values
        ):
            location_details = 'location'
            setting['Levels of government'] = ', '.join(
                [
                    x
                    for x in df.loc[df.value.notna()].loc[
                        df.item
                        == 'Names of level(s) of government policy included the policy checklist',
                        'location',
                    ]
                    if not x.startswith('Other')
                ],
            )
        else:
            location_details = 'item'
            setting['Levels of government'] = df.loc[
                df['item'].str.startswith(
                    'Governments included in the policy checklist:',
                ),
                'value',
            ].values[0]
        setting['City'] = df.loc[
            df[location_details].str.replace(':', '') == 'City',
            'value',
        ].values[0]
        setting['Region'] = df.loc[
            df[location_details]
            .str.replace(':', '')
            .str.lower()
            .str.endswith('region')
            .fillna(False),
            'value',
        ].values[0]
        setting['Country'] = df.loc[
            df[location_details].str.replace(':', '') == 'Country',
            'value',
        ].values[0]
        setting['Environmental disaster context'] = {}
        disasters = [
            'Severe storms',
            'Floods',
            'Bushfires/wildfires',
            'Heatwaves',
            'Extreme cold',
            'Typhoons',
            'Hurricanes',
            'Cyclones',
            'Earthquakes',
        ]
        for disaster in disasters:
            setting['Environmental disaster context'][disaster] = df.loc[
                (df['item'].str.strip() == disaster)
                & (df['item'].str.strip() != 'Other (please specify)'),
                'value',
            ].values[0]
        setting['Environmental disaster context']['Other'] = df.loc[
            df[location_details] == 'Other (please specify)',
            'value',
        ].values[0]
        setting['Environmental disaster context'] = '\n'.join(
            [
                f'{x}: {setting["Environmental disaster context"][x]}'
                for x in setting['Environmental disaster context']
                if str(setting['Environmental disaster context'][x]) != 'nan'
            ],
        )
        # Extract City context if available
        city_context_rows = df.loc[
            df[location_details]
            .str.strip()
            .str.startswith('City context')
            .fillna(False),
            'value',
        ].dropna()
        if len(city_context_rows) > 0:
            setting['City context'] = city_context_rows.values[0]
            if pd.isna(setting['City context']):
                setting['City context'] = ''
        else:
            setting['City context'] = ''

        # Extract Demographics and health equity if available
        demographics_rows = df.loc[
            df[location_details]
            .str.strip()
            .str.startswith('Demographics and health equity')
            .fillna(False),
            'value',
        ].dropna()
        if len(demographics_rows) > 0:
            setting['Demographics and health equity'] = (
                demographics_rows.values[0]
            )
            if pd.isna(setting['Demographics and health equity']):
                setting['Demographics and health equity'] = ''
        else:
            setting['Demographics and health equity'] = ''
        for x in setting:
            if setting[x] == '':
                setting[x] = 'Not specified'
        return setting
    except Exception as e:
        print(
            f'  Error reading policy checklist "Collection details" worksheet; please ensure that this has been completed.\nSpecific error: {e}',
        )
        return None


def get_policy_checklist_item(
    policy_review_setting,
    phrases,
    item='Levels of government',
):
    """Get policy checklist items (e.g. 'Levels of government' or 'Environmnetal disaster context')."""
    if policy_review_setting is None:
        return []
    levels = policy_review_setting[item].split('\n')
    if len(levels) == 0:
        return []
    elif len(levels) == 1:
        return levels
    elif len(levels) > 1:
        levels_clean = [
            phrases[level[0].strip()].strip()
            for level in [
                x.split(': ')
                for x in levels
                if not (
                    x.startswith('Other') or x.startswith('(Please indicate')
                )
            ]
            if str(level[1]).strip()
            not in ['No', 'missing', 'nan', 'None', 'N/A', '']
        ]
        levels_clean = levels_clean + [
            x.replace('Other: ', '').lower()
            for x in levels
            if x.startswith('Other: ')
        ]
        return levels_clean


def summarise_policy(series_or_df):
    """
    Summarise policy evaluation for 'identified', 'aligns', 'measurable'.

    Input: pandas Series or DataFrame with these three fields.
    For each field:
      - Return '✔' if all values are '✔'
      - Return '-' if all values are '-'
      - Else return '✘'
    Returns a dictionary: {name: {field: result, ...}}
    """
    if isinstance(series_or_df, pd.Series):
        summary = {
            col: series_or_df[col]
            for col in ['identified', 'aligns', 'measurable']
            if col in series_or_df
        }
        return summary
    elif isinstance(series_or_df, pd.DataFrame):
        summary = {}
        for col in ['identified', 'aligns', 'measurable']:
            values = series_or_df[col]
            if (values == '✔').all():
                summary[col] = '✔'
            elif (values == '-').all():
                summary[col] = '-'
            else:
                summary[col] = '✘'
        return summary
    else:
        raise TypeError('Input must be a pandas Series or DataFrame')


# PDF layout set up
class PDF_Policy_Report(FPDF):
    """PDF report class for analysis report."""

    def __init__(self, policy_checklist, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        self.file = policy_checklist

    def generate_policy_report(self):
        """Generate analysis report."""
        file_path = generate_policy_report(self.file)
        return file_path
