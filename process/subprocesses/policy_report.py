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
        ghsci.policies,
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
            """Policy.astype('str') not in ['No','','nan','NaN'] and qualifier!='No' and `Evidence-informed threshold`.astype('str') not in ['No']""",
        )['Policy'],
    )
    does_not_align = any(
        policy.query(
            """Policy.astype('str') not in ['No','','nan','NaN'] and qualifier=='No'""",
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


def policy_data_setup(xlsx: str, policies: dict):
    """Returns a dictionary of policy data."""
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
                policy_measure = audit.query(f'Measures == "{measure}"')
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


def get_policy_checklist(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    from subprocesses.ghsci import policies

    try:
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
        df = df.apply(lambda x: x.str.strip() if x.dtype == 'object' else x)
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
        return df
    except Exception as e:
        print(
            f'  Error reading policy checklist; please ensure these have been completed.  Specific error: {e}',
        )
        return None


def get_policy_setting(xlsx) -> dict:
    """Get and format policy checklist from Excel into series of DataFrames organised by indicator and measure in a dictionary."""
    try:
        df = pd.read_excel(xlsx, sheet_name='Collection details', header=3)
        if len(df.columns) < 3:
            print(
                'Policy checklist collection details appear not to have completed (no values found in column C); please check the specified file has been completed.',
            )
            return None
        # Strip redundant white space (e.g. at start or end of cell values that could impede matching or formatting)
        df.columns = ['item', 'location', 'value']
        df.loc[:, 'item'] = df.loc[:, 'item'].ffill()
        setting = {}
        setting['Person(s)'] = df.loc[
            df['item'] == 'Name of person(s) completing checklist:',
            'value',
        ].values[0]
        setting['E-mail'] = df.loc[
            df['item'] == 'Email address(es):',
            'value',
        ].values[0]
        setting['Date'] = df.loc[
            df['item'] == 'Date completed:',
            'value',
        ].values[0]
        try:
            setting['Date'] = setting['Date'].strftime('%Y')
        except Exception:
            pass
        setting['City'] = df.loc[
            df['item'] == 'City:',
            'value',
        ].values[0]
        setting['Region'] = df.loc[
            df['item'] == 'State/province/county/region:',
            'value',
        ].values[0]
        setting['Country'] = df.loc[
            df['item'] == 'Country:',
            'value',
        ].values[0]
        setting['Levels of government'] = df.loc[
            df['item'].str.startswith(
                'Governments included in the policy checklist:',
            ),
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
            df['item'] == 'Other (please specify)',
            'value',
        ].values[0]
        setting['Environmental disaster context'] = '\n'.join(
            [
                f'{x}: {setting["Environmental disaster context"][x]}'
                for x in setting['Environmental disaster context']
                if str(setting['Environmental disaster context'][x]) != 'nan'
            ],
        )
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
